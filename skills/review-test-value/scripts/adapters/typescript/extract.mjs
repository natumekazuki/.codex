import process from "node:process";
import ts from "typescript";

function readStdin() {
  return new Promise((resolve, reject) => {
    let value = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      value += chunk;
    });
    process.stdin.on("end", () => resolve(value));
    process.stdin.on("error", reject);
  });
}

function lineNumber(sourceFile, position) {
  return sourceFile.getLineAndCharacterOfPosition(position).line + 1;
}

function lineIndent(source, sourceFile, position) {
  const location = sourceFile.getLineAndCharacterOfPosition(position);
  const lineStart = sourceFile.getPositionOfLineAndCharacter(location.line, 0);
  const prefix = source.slice(lineStart, position);
  return /^\s*$/.test(prefix) ? prefix : null;
}

function staticTitle(node) {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
    return node.text;
  }
  return null;
}

function propertyParts(expression) {
  if (ts.isIdentifier(expression)) {
    return [expression.text];
  }
  if (ts.isPropertyAccessExpression(expression)) {
    const left = propertyParts(expression.expression);
    return left === null ? null : [...left, expression.name.text];
  }
  return null;
}

function testCallInfo(node) {
  if (ts.isCallExpression(node.parent) && node.parent.expression === node) {
    return null;
  }
  let expression = node.expression;
  let parameterized = false;
  let parameterizedRoot = null;
  if (ts.isCallExpression(expression)) {
    const innerParts = propertyParts(expression.expression);
    if (
      innerParts !== null &&
      innerParts.length === 2 &&
      ["test", "it"].includes(innerParts[0]) &&
      innerParts[1] === "each"
    ) {
      parameterized = true;
      parameterizedRoot = innerParts[0];
    }
  }

  const parts = parameterizedRoot === null ? propertyParts(expression) : [parameterizedRoot];
  if (parts === null || !["test", "it"].includes(parts[0])) {
    return null;
  }
  const modifiers = parts.slice(1);
  const supportedModifiers = new Set(["only", "skip", "todo", "fixme", "fail"]);
  if (modifiers.some((part) => !supportedModifiers.has(part))) {
    return {
      supported: false,
      message: `unsupported test declaration modifier: ${modifiers.join(".")}`,
    };
  }
  return { supported: true, parameterized, titleArgument: node.arguments[0] };
}

function describeCallInfo(node) {
  const parts = propertyParts(node.expression);
  if (parts === null) {
    return null;
  }
  const isDescribe =
    parts[0] === "describe" ||
    (parts[0] === "test" && parts.length >= 2 && parts[1] === "describe");
  if (!isDescribe) {
    return null;
  }
  const modifierStart = parts[0] === "describe" ? 1 : 2;
  if (parts.length > modifierStart) {
    return {
      supported: false,
      message: `unsupported describe modifier: ${parts.slice(modifierStart).join(".")}`,
    };
  }
  const title = staticTitle(node.arguments[0]);
  if (title === null) {
    return {
      supported: false,
      message: "describe declaration title must be a static string",
    };
  }
  return { supported: true, title };
}

function enclosingDescribeTitles(node) {
  const titles = [];
  let current = node.parent;
  while (current !== undefined) {
    if (ts.isCallExpression(current)) {
      const info = describeCallInfo(current);
      if (info !== null) {
        if (!info.supported) {
          return null;
        }
        titles.push(info.title);
      }
    }
    current = current.parent;
  }
  return titles.reverse();
}

function expressionStatement(node) {
  return ts.isExpressionStatement(node.parent) ? node.parent : node;
}

function collectComments(source, sourceFile, scriptKind) {
  const comments = [];
  const languageVariant =
    scriptKind === ts.ScriptKind.TSX ? ts.LanguageVariant.JSX : ts.LanguageVariant.Standard;
  const scanner = ts.createScanner(
    ts.ScriptTarget.Latest,
    false,
    languageVariant,
    source,
  );
  while (scanner.scan() !== ts.SyntaxKind.EndOfFileToken) {
    if (scanner.getToken() !== ts.SyntaxKind.SingleLineCommentTrivia) {
      continue;
    }
    const position = scanner.getTokenPos();
    const indent = lineIndent(source, sourceFile, position);
    if (indent === null) {
      continue;
    }
    let text = scanner.getTokenText().slice(2);
    if (text.startsWith(" ")) {
      text = text.slice(1);
    }
    comments.push({ line: lineNumber(sourceFile, position), indent, text });
  }
  return comments;
}

function collectDeclarations(sourceFile) {
  const declarations = [];
  const diagnostics = [];

  function visit(node) {
    if (ts.isCallExpression(node)) {
      const describeInfo = describeCallInfo(node);
      if (describeInfo !== null) {
        if (!describeInfo.supported) {
          diagnostics.push({
            code: "TEST_DECLARATION_UNSUPPORTED",
            line: lineNumber(sourceFile, node.getStart(sourceFile, false)),
            message: describeInfo.message,
          });
        }
        ts.forEachChild(node, visit);
        return;
      }
      const info = testCallInfo(node);
      if (info !== null) {
        if (!info.supported) {
          diagnostics.push({
            code: "TEST_DECLARATION_UNSUPPORTED",
            line: lineNumber(sourceFile, node.getStart(sourceFile, false)),
            message: info.message,
          });
          ts.forEachChild(node, visit);
          return;
        }
        const statement = expressionStatement(node);
        const start = statement.getStart(sourceFile, false);
        const title = info.titleArgument ? staticTitle(info.titleArgument) : null;
        if (title === null) {
          diagnostics.push({
            code: "TEST_DECLARATION_UNSUPPORTED",
            line: lineNumber(sourceFile, start),
            message: "test declaration title must be a static string",
          });
        } else {
          const describeTitles = enclosingDescribeTitles(node);
          if (describeTitles === null) {
            ts.forEachChild(node, visit);
            return;
          }
          const symbol = [...describeTitles, title].join(" > ");
          declarations.push({
            symbol,
            start_line: lineNumber(sourceFile, start),
            end_line: lineNumber(sourceFile, statement.getEnd()),
            indent: lineIndent(sourceFile.text, sourceFile, start) ?? "",
          });
        }
      }
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return { declarations, diagnostics };
}

const source = await readStdin();
const extension = process.argv[2] ?? ".ts";
const scriptKind = extension === ".tsx" ? ts.ScriptKind.TSX : ts.ScriptKind.TS;
const sourceFile = ts.createSourceFile(
  `input${extension}`,
  source,
  ts.ScriptTarget.Latest,
  true,
  scriptKind,
);
const syntaxDiagnostics = (sourceFile.parseDiagnostics ?? []).map((item) => ({
  code: "SOURCE_SYNTAX_ERROR",
  line: lineNumber(sourceFile, item.start ?? 0),
  message: ts.flattenDiagnosticMessageText(item.messageText, " "),
}));
const analysis = collectDeclarations(sourceFile);
process.stdout.write(
  JSON.stringify({
    declarations: analysis.declarations,
    comments: collectComments(source, sourceFile, scriptKind),
    diagnostics: [...syntaxDiagnostics, ...analysis.diagnostics],
  }),
);
