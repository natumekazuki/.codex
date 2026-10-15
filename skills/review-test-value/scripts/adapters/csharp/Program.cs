using System.Text;
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

static bool IsTestAttributeName(string name)
{
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

static bool IsTestAttribute(AttributeSyntax attribute) =>
    IsTestAttributeName(AttributeIdentifier(attribute.Name));

static bool IsTestMethod(MethodDeclarationSyntax method) =>
    method.AttributeLists.SelectMany(list => list.Attributes).Any(IsTestAttribute);

static ExpressionSyntax? ConditionalExpression(DirectiveTriviaSyntax directive) =>
    directive switch
    {
        IfDirectiveTriviaSyntax item => item.Condition,
        ElifDirectiveTriviaSyntax item => item.Condition,
        _ => null,
    };

static bool RequiresProjectSpecificSymbols(DirectiveTriviaSyntax directive) =>
    ConditionalExpression(directive)?
        .DescendantNodesAndSelf()
        .OfType<IdentifierNameSyntax>()
        .Any() == true;

static SyntaxToken HeaderEnd(SyntaxNode node) => node switch
{
    BaseTypeDeclarationSyntax type when type.OpenBraceToken.RawKind != 0 && !type.OpenBraceToken.IsMissing =>
        type.OpenBraceToken,
    NamespaceDeclarationSyntax space => space.OpenBraceToken,
    FileScopedNamespaceDeclarationSyntax space => space.SemicolonToken,
    BaseMethodDeclarationSyntax method =>
        method.Body?.OpenBraceToken ?? method.ExpressionBody?.ArrowToken ?? method.SemicolonToken,
    LocalFunctionStatementSyntax local =>
        local.Body?.OpenBraceToken ?? local.ExpressionBody?.ArrowToken ?? local.SemicolonToken,
    BasePropertyDeclarationSyntax property when property.AccessorList is not null =>
        property.AccessorList.OpenBraceToken,
    PropertyDeclarationSyntax property when property.ExpressionBody is not null =>
        property.ExpressionBody.ArrowToken,
    IndexerDeclarationSyntax indexer when indexer.ExpressionBody is not null =>
        indexer.ExpressionBody.ArrowToken,
    _ => node.GetLastToken(),
};

static bool HasUnbalancedDelimiters(IEnumerable<SyntaxToken> tokens)
{
    var closing = new Stack<SyntaxKind>();
    foreach (var token in tokens)
    {
        var expected = token.Kind() switch
        {
            SyntaxKind.OpenBraceToken => SyntaxKind.CloseBraceToken,
            SyntaxKind.OpenBracketToken => SyntaxKind.CloseBracketToken,
            SyntaxKind.OpenParenToken => SyntaxKind.CloseParenToken,
            _ => SyntaxKind.None,
        };
        if (expected != SyntaxKind.None)
        {
            closing.Push(expected);
        }
        else if (token.Kind() is SyntaxKind.CloseBraceToken or SyntaxKind.CloseBracketToken or SyntaxKind.CloseParenToken)
        {
            if (!closing.TryPop(out var kind) || kind != token.Kind())
            {
                return true;
            }
        }
    }
    return closing.Count != 0;
}

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

Console.InputEncoding = Encoding.UTF8;
var source = await Console.In.ReadToEndAsync();
var tree = CSharpSyntaxTree.ParseText(source, new CSharpParseOptions(LanguageVersion.Latest));
var root = await tree.GetRootAsync();
var diagnostics = tree.GetDiagnostics()
    .Where(item => item.Severity == DiagnosticSeverity.Error)
    .Select(item => new
    {
        code = "SOURCE_SYNTAX_ERROR",
        line = item.Location == Location.None ? 0 : item.Location.GetLineSpan().StartLinePosition.Line + 1,
        message = DiagnosticProjection.Message(item),
    })
    .Cast<object>()
    .ToList();

var trivia = root.DescendantTrivia(descendIntoTrivia: true).ToList();
var conditionalGroups = trivia
    .Select(trivia => trivia.GetStructure())
    .OfType<IfDirectiveTriviaSyntax>()
    .Select(directive => new
    {
        directive,
        related = directive.GetRelatedDirectives(),
    })
    .Where(group => group.related.Any(RequiresProjectSpecificSymbols))
    .Select(group => new
    {
        group.directive,
        start = group.directive.SpanStart,
        end = group.related.Last().Span.End,
    })
    .ToList();

// Lex inactive fragments separately: joining alternative branches can turn code
// into another branch's comment or string and hide a test attribute.
var tokens = root.DescendantTokens().ToList();
var uncertainSpans = new List<TextSpan>();
foreach (var disabled in trivia.Where(item => item.IsKind(SyntaxKind.DisabledTextTrivia)))
{
    var inactiveTokens = SyntaxFactory.ParseTokens(
        disabled.ToString(), initialTokenPosition: disabled.SpanStart).ToList();
    tokens.AddRange(inactiveTokens);
    if (HasUnbalancedDelimiters(inactiveTokens)
        || (inactiveTokens.Any(token => token.IsKind(SyntaxKind.NamespaceKeyword))
            && CSharpSyntaxTree.ParseText(disabled.ToString()).GetRoot()
                .DescendantNodes().OfType<FileScopedNamespaceDeclarationSyntax>().Any())
        || inactiveTokens.Any(token => token.ContainsDiagnostics
        || token.LeadingTrivia.Concat(token.TrailingTrivia)
            .Any(item => item.IsKind(SyntaxKind.DisabledTextTrivia))))
    {
        uncertainSpans.Add(disabled.Span);
    }
}
var candidates = tokens
    .Where(token => token.IsKind(SyntaxKind.IdentifierToken) && IsTestAttributeName(token.ValueText))
    .Select(token => token.SpanStart)
    .ToList();
// The lexer returns an interpolated string as one token. Inspect its expression
// syntax as well, since interpolation expressions can contain local functions.
foreach (var token in tokens.Where(token => token.IsKind(SyntaxKind.InterpolatedStringToken)))
{
    var expression = SyntaxFactory.ParseExpression(token.Text);
    if (expression.ContainsDiagnostics)
    {
        uncertainSpans.Add(token.Span);
    }
    candidates.AddRange(expression.DescendantTokens()
        .Where(item => item.IsKind(SyntaxKind.IdentifierToken) && IsTestAttributeName(item.ValueText))
        .Select(item => token.SpanStart + item.SpanStart));
}
var headers = root.DescendantNodes()
    .Where(node => node is MemberDeclarationSyntax or LocalFunctionStatementSyntax)
    .Where(node => !node.Ancestors().OfType<AttributeSyntax>().Any())
    .Select(node => new { node, end = HeaderEnd(node) })
    .Where(header => header.end.RawKind != 0 && header.end.Span.End >= header.node.SpanStart)
    .ToList();
bool IsInSymbolGroup(int position) =>
    conditionalGroups.Any(group => position >= group.start && position < group.end);
// Only declaration boundaries outside every symbol-dependent group can end a
// possible attribute prefix. A delimiter in just one alternative is not proof.
var stableBoundaries = headers
    .SelectMany(header => new[] { header.end, header.node.GetLastToken() })
    .Where(token => !token.IsMissing && !IsInSymbolGroup(token.SpanStart))
    .Select(token => token.Span.End)
    .Distinct()
    .Order()
    .ToList();
var candidateEnds = candidates.Select(start => new
{
    start,
    end = stableBoundaries.FirstOrDefault(position => position > start, source.Length),
}).ToList();
var unsupportedGroups = conditionalGroups.Where(group =>
{
    var span = TextSpan.FromBounds(group.start, group.end);
    return candidateEnds.Any(candidate => candidate.start < group.end && candidate.end > group.start)
        || uncertainSpans.Any(span.OverlapsWith)
        || headers.Any(header =>
            span.OverlapsWith(TextSpan.FromBounds(header.node.SpanStart, header.end.Span.End))
            && !span.Contains(header.node.Span)
            && candidates.Any(position => header.node.FullSpan.Contains(position)));
}).ToList();
var conditionalTestDeclarations = root.DescendantNodes().Where(node => node switch
{
    MethodDeclarationSyntax method => IsTestMethod(method),
    LocalFunctionStatementSyntax local => local.AttributeLists
        .SelectMany(list => list.Attributes).Any(IsTestAttribute),
    _ => false,
}).ToList();
foreach (var group in unsupportedGroups)
{
    var span = TextSpan.FromBounds(group.start, group.end);
    var excluded = conditionalTestDeclarations.Where(node => node.Span.OverlapsWith(span)).ToList();
    diagnostics.Add(new
    {
        code = "TEST_DECLARATION_UNSUPPORTED",
        line = LineNumber(tree, group.start),
        // Git selection must cover every excluded declaration, including its metadata.
        start_line = LineNumber(tree, excluded.Select(node => node.FullSpan.Start)
            .Append(group.start).Min()),
        end_line = LineNumber(tree, excluded.Select(node => node.Span.End)
            .Append(group.end).Max()),
        message = "symbol-dependent conditional compilation may affect a test declaration",
    });
}

bool IsInsideUnsupportedConditional(SyntaxNode node) =>
    unsupportedGroups.Any(group => node.Span.OverlapsWith(TextSpan.FromBounds(group.start, group.end)));

var declarations = new List<object>();
var methods = root.DescendantNodes()
    .OfType<MethodDeclarationSyntax>()
    .Where(method => !IsInsideUnsupportedConditional(method));
var testMethods = methods.Where(IsTestMethod)
    .Select(method =>
    {
        var start = method.AttributeLists.Count > 0
            ? method.AttributeLists.Min(list => list.SpanStart)
            : method.SpanStart;
        return new
        {
            method,
            start,
            indent = LineIndent(source, tree, start),
            line = LineNumber(tree, start),
        };
    })
    .ToList();
var unsupportedDeclarationLines = testMethods
    .Where(item => item.indent is null)
    .Select(item => item.line)
    .ToHashSet();
foreach (var line in unsupportedDeclarationLines.Order())
{
    diagnostics.Add(new
    {
        code = "TEST_DECLARATION_UNSUPPORTED",
        line,
        end_line = testMethods
            .Where(item => item.line == line)
            .Max(item => LineNumber(tree, item.method.Span.End)),
        message = "test declaration must begin after indentation only",
    });
}
foreach (var item in testMethods)
{
    if (unsupportedDeclarationLines.Contains(item.line))
    {
        continue;
    }
    declarations.Add(new
    {
        symbol = QualifiedSymbol(item.method),
        start_line = item.line,
        end_line = LineNumber(tree, item.method.Span.End),
        indent = item.indent,
    });
}

foreach (var local in root.DescendantNodes().OfType<LocalFunctionStatementSyntax>())
{
    if (IsInsideUnsupportedConditional(local))
    {
        continue;
    }
    if (!local.AttributeLists.SelectMany(list => list.Attributes).Any(IsTestAttribute))
    {
        continue;
    }
    diagnostics.Add(new
    {
        code = "TEST_DECLARATION_UNSUPPORTED",
        line = LineNumber(tree, local.SpanStart),
        end_line = LineNumber(tree, local.Span.End),
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
