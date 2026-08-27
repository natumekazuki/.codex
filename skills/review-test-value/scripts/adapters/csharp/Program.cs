using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Text;

static int LineNumber(SyntaxTree tree, int position) =>
    tree.GetLineSpan(new TextSpan(position, 0)).StartLinePosition.Line + 1;

static string? LineIndent(string source, SyntaxTree tree, int position)
{
    var line = tree.GetText().Lines.GetLineFromPosition(position);
    var prefix = source[line.Start..position];
    return prefix.All(char.IsWhiteSpace) ? prefix : null;
}

static string AttributeIdentifier(NameSyntax name) => name switch
{
    IdentifierNameSyntax identifier => identifier.Identifier.ValueText,
    GenericNameSyntax generic => generic.Identifier.ValueText,
    QualifiedNameSyntax qualified => AttributeIdentifier(qualified.Right),
    AliasQualifiedNameSyntax alias => AttributeIdentifier(alias.Name),
    _ => name.ToString(),
};

static bool IsTestAttribute(AttributeSyntax attribute)
{
    var name = AttributeIdentifier(attribute.Name);
    if (name.EndsWith("Attribute", StringComparison.Ordinal))
    {
        name = name[..^"Attribute".Length];
    }
    return new HashSet<string>(StringComparer.Ordinal)
    {
        "Fact",
        "Theory",
        "Test",
        "TestCase",
        "TestCaseSource",
        "TestMethod",
        "DataTestMethod",
    }.Contains(name);
}

static bool IsTestMethod(MethodDeclarationSyntax method) =>
    method.AttributeLists.SelectMany(list => list.Attributes).Any(IsTestAttribute);

static string QualifiedSymbol(MethodDeclarationSyntax method)
{
    var namespaces = method.Ancestors()
        .OfType<BaseNamespaceDeclarationSyntax>()
        .Select(item => item.Name.ToString())
        .Reverse();
    var types = method.Ancestors()
        .OfType<TypeDeclarationSyntax>()
        .Select(type => type.Identifier.ValueText)
        .Reverse();
    return string.Join(".", namespaces.Concat(types).Append(method.Identifier.ValueText));
}

var source = await Console.In.ReadToEndAsync();
var tree = CSharpSyntaxTree.ParseText(source, new CSharpParseOptions(LanguageVersion.Latest));
var root = await tree.GetRootAsync();
var diagnostics = tree.GetDiagnostics()
    .Where(item => item.Severity == DiagnosticSeverity.Error)
    .Select(item => new
    {
        code = "SOURCE_SYNTAX_ERROR",
        line = item.Location == Location.None ? 0 : item.Location.GetLineSpan().StartLinePosition.Line + 1,
        message = item.GetMessage(),
    })
    .Cast<object>()
    .ToList();

var conditionalDirective = root.DescendantTrivia(descendIntoTrivia: true)
    .FirstOrDefault(trivia => trivia.IsKind(SyntaxKind.IfDirectiveTrivia));
var hasConditionalCompilation = conditionalDirective != default;
if (hasConditionalCompilation)
{
    diagnostics.Add(new
    {
        code = "TEST_DECLARATION_UNSUPPORTED",
        line = LineNumber(tree, conditionalDirective.SpanStart),
        message = "conditional compilation requires project-specific preprocessor symbols",
    });
}

var declarations = (hasConditionalCompilation
        ? Enumerable.Empty<MethodDeclarationSyntax>()
        : root.DescendantNodes().OfType<MethodDeclarationSyntax>())
    .Where(IsTestMethod)
    .Select(method =>
    {
        var start = method.AttributeLists.Count > 0
            ? method.AttributeLists.Min(list => list.SpanStart)
            : method.SpanStart;
        return new
        {
            symbol = QualifiedSymbol(method),
            start_line = LineNumber(tree, start),
            end_line = LineNumber(tree, method.Span.End),
            indent = LineIndent(source, tree, start) ?? "",
        };
    })
    .ToList();

foreach (var local in root.DescendantNodes().OfType<LocalFunctionStatementSyntax>())
{
    if (!local.AttributeLists.SelectMany(list => list.Attributes).Any(IsTestAttribute))
    {
        continue;
    }
    diagnostics.Add(new
    {
        code = "TEST_DECLARATION_UNSUPPORTED",
        line = LineNumber(tree, local.SpanStart),
        message = "test attribute is attached to a local function",
    });
}

var comments = root.DescendantTrivia(descendIntoTrivia: true)
    .Where(trivia => trivia.IsKind(SyntaxKind.SingleLineCommentTrivia))
    .Select(trivia =>
    {
        var indent = LineIndent(source, tree, trivia.SpanStart);
        if (indent is null)
        {
            return null;
        }
        var text = trivia.ToString()[2..];
        if (text.StartsWith(' '))
        {
            text = text[1..];
        }
        return new
        {
            line = LineNumber(tree, trivia.SpanStart),
            indent,
            text,
        };
    })
    .Where(item => item is not null)
    .ToList();

Console.Write(JsonSerializer.Serialize(new { declarations, comments, diagnostics }));
