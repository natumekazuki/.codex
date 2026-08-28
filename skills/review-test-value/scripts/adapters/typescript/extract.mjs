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

function declarationArguments(args) {
  // v1 is syntax-only: a static first argument distinguishes declaration overloads.
  return staticTitle(args[0]) === null ? null : { titleArgument: args[0] };
}

function isTransparentExpression(node) {
  return (
    ts.isParenthesizedExpression(node) ||
    ts.isAsExpression(node) ||
    ts.isTypeAssertionExpression(node) ||
    ts.isNonNullExpression(node) ||
    ts.isSatisfiesExpression(node)
  );
}

function unwrapTransparentExpression(node) {
  let current = node;
  while (isTransparentExpression(current)) {
    current = current.expression;
  }
  return current;
}

function isInnerCalleeCall(node) {
  let expression = node;
  let parent = node.parent;
  while (true) {
    if (isTransparentExpression(parent) && parent.expression === expression) {
      expression = parent;
      parent = parent.parent;
      continue;
    }
    if (ts.isPropertyAccessExpression(parent) && parent.expression === expression) {
      expression = parent;
      parent = parent.parent;
      continue;
    }
    break;
  }
  return ts.isCallExpression(parent) && parent.expression === expression;
}

const nonDeclarationApis = new Set([
  "abort",
  "afterAll",
  "afterEach",
  "beforeAll",
  "beforeEach",
  "expect",
  "extend",
  "info",
  "setTimeout",
  "slow",
  "step",
  "step.skip",
  "use",
]);

function terminalBuilderInfo(expression) {
  const trailingMembers = [];
  let current = unwrapTransparentExpression(expression);
  while (ts.isPropertyAccessExpression(current)) {
    trailingMembers.unshift(current.name.text);
    current = unwrapTransparentExpression(current.expression);
  }
  if (ts.isCallExpression(current)) {
    return {
      kind: "call",
      parts: propertyParts(current.expression),
      trailingMembers,
    };
  }
  if (ts.isTaggedTemplateExpression(current)) {
    return {
      kind: "tagged",
      parts: propertyParts(current.tag),
      trailingMembers,
    };
  }
  return null;
}

function testCallInfo(node) {
  if (isInnerCalleeCall(node)) {
    return null;
  }
  const builder = terminalBuilderInfo(node.expression);
  const parts = builder === null ? propertyParts(node.expression) : builder.parts;
  if (parts === null || !["test", "it"].includes(parts[0])) {
    return null;
  }

  const members = parts.slice(1);
  if (builder !== null) {
    const memberPath = members.join(".");
    if (parts[0] === "test" && nonDeclarationApis.has(memberPath)) {
      return { kind: "ignore" };
    }
    const chainPath = [...members, ...builder.trailingMembers].join(".");
    if (builder.kind === "tagged") {
      return {
        kind: "unsupported",
        message: `unsupported tagged test declaration call chain: ${chainPath}`,
      };
    }
    if (builder.trailingMembers.length > 0) {
      return {
        kind: "unsupported",
        message: `unsupported test declaration call chain: ${chainPath}`,
      };
    }
    if (members.at(-1) !== "each") {
      return {
        kind: "unsupported",
        message: `unsupported test declaration call chain: ${members.join(".")}`,
      };
    }
    const modifiers = members.slice(0, -1);
    if (modifiers.length > 0) {
      return {
        kind: "unsupported",
        message: `unsupported test declaration modifier: ${modifiers.join(".")}`,
      };
    }
    const declaration = declarationArguments(node.arguments);
    return declaration === null
      ? {
          kind: "unsupported",
          message: "parameterized test declaration requires a static title",
        }
      : { kind: "declaration", parameterized: true, ...declaration };
  }

  if (members.length === 0) {
    const declaration = declarationArguments(node.arguments);
    return declaration === null
      ? {
          kind: "unsupported",
          message: "test declaration requires a static title",
        }
      : { kind: "declaration", parameterized: false, ...declaration };
  }

  const memberPath = members.join(".");
  if (parts[0] === "test" && nonDeclarationApis.has(memberPath)) {
    return { kind: "ignore" };
  }

  const declarationModifiers = new Set(["only", "skip", "todo", "fixme", "fail", "fail.only"]);
  if (!declarationModifiers.has(memberPath)) {
    return {
      kind: "unsupported",
      message: `unsupported test declaration modifier: ${memberPath}`,
    };
  }

  const declaration = declarationArguments(node.arguments);
  if (declaration !== null) {
    return { kind: "declaration", parameterized: false, ...declaration };
  }
  if (parts[0] === "test" && ["skip", "fixme", "fail"].includes(memberPath)) {
    return { kind: "ignore" };
  }
  return {
    kind: "unsupported",
    message: `unsupported ${memberPath} test declaration arguments`,
  };
}

function describeCallInfo(node) {
  if (isInnerCalleeCall(node)) {
    return null;
  }
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
  const modifiers = parts.slice(modifierStart);
  const modifierPath = modifiers.join(".");
  if (parts[0] === "test" && modifierPath === "configure") {
    return { kind: "ignore" };
  }
  const supportedModifiers = new Set(["", "only", "skip", "fixme", "parallel", "serial", "parallel.only", "serial.only"]);
  if (!supportedModifiers.has(modifierPath)) {
    return {
      kind: "unsupported",
      message: `unsupported describe modifier: ${modifierPath}`,
    };
  }
  const title = staticTitle(node.arguments[0]);
  if (title === null) {
    return {
      kind: "unsupported",
      message: "describe declaration title must be a static string",
    };
  }
  return { kind: "declaration", title };
}

function enclosingDescribeTitles(node) {
  const titles = [];
  let current = node.parent;
  while (current !== undefined) {
    if (ts.isCallExpression(current)) {
      const info = describeCallInfo(current);
      if (info !== null) {
        if (info.kind === "unsupported") {
          return null;
        }
        if (info.kind === "declaration") {
          titles.push(info.title);
        }
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
  const unsupportedDeclarationLines = new Set();

  function visit(node) {
    if (ts.isCallExpression(node)) {
      const describeInfo = describeCallInfo(node);
      if (describeInfo !== null) {
        if (describeInfo.kind === "unsupported") {
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
        if (info.kind === "unsupported") {
          diagnostics.push({
            code: "TEST_DECLARATION_UNSUPPORTED",
            line: lineNumber(sourceFile, node.getStart(sourceFile, false)),
            message: info.message,
          });
          ts.forEachChild(node, visit);
          return;
        }
        if (info.kind === "ignore") {
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
          const indent = lineIndent(sourceFile.text, sourceFile, start);
          if (indent === null) {
            const declarationLine = lineNumber(sourceFile, start);
            if (!unsupportedDeclarationLines.has(declarationLine)) {
              unsupportedDeclarationLines.add(declarationLine);
              diagnostics.push({
                code: "TEST_DECLARATION_UNSUPPORTED",
                line: declarationLine,
                message: "test declaration must begin after indentation only",
              });
            }
            ts.forEachChild(node, visit);
            return;
          }
          declarations.push({
            symbol,
            start_line: lineNumber(sourceFile, start),
            end_line: lineNumber(sourceFile, statement.getEnd()),
            indent,
          });
        }
      }
    }
    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
  return {
    declarations: declarations.filter(
      (declaration) => !unsupportedDeclarationLines.has(declaration.start_line),
    ),
    diagnostics,
  };
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
