using System.Globalization;
using Microsoft.CodeAnalysis;

public static class DiagnosticProjection
{
    public static string Message(Diagnostic diagnostic) =>
        diagnostic.GetMessage(CultureInfo.InvariantCulture);
}
