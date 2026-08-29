using System.Globalization;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

var diagnostic = CSharpSyntaxTree.ParseText("public class Broken {")
    .GetDiagnostics()
    .Single(item => item.Severity == DiagnosticSeverity.Error);

string ProjectWithUiCulture(string cultureName)
{
    CultureInfo.CurrentUICulture = CultureInfo.GetCultureInfo(cultureName);
    return DiagnosticProjection.Message(diagnostic);
}

var english = ProjectWithUiCulture("en-US");
var japanese = ProjectWithUiCulture("ja-JP");
if (!string.Equals(english, japanese, StringComparison.Ordinal))
{
    Console.Error.WriteLine("diagnostic projection depends on CurrentUICulture");
    return 1;
}

return 0;
