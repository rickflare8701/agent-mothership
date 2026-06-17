Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public class RpcMgmtTest {
    [DllImport("rpcrt4.dll", CharSet = CharSet.Unicode)]
    static extern int RpcStringBindingCompose(string a, string b, string c, string d, string e, out string f);
    [DllImport("rpcrt4.dll", CharSet = CharSet.Unicode)]
    static extern int RpcBindingFromStringBinding(string a, out IntPtr b);
    [DllImport("rpcrt4.dll")]
    static extern int RpcBindingFree(ref IntPtr a);
    [DllImport("rpcrt4.dll")]
    static extern int RpcMgmtIsServerListening(IntPtr a);
    [DllImport("rpcrt4.dll", CharSet = CharSet.Unicode)]
    static extern int RpcMgmtInqServerPrincName(IntPtr a, uint b, out string c);

    static string[] eps = { "ST.DispatchEvents","STDisp-EventSink","STDisp-FTQ","STN.Dispatch","STN.Core","STN.Core.Security" };

    public static string Run() {
        var sb = new System.Text.StringBuilder();
        foreach (var ep in eps) {
            string s; int r = RpcStringBindingCompose(null, "ncalrpc", null, ep, null, out s);
            if (r != 0) { sb.AppendLine(ep + ": compose=0x" + r.ToString("X8")); continue; }
            IntPtr b; r = RpcBindingFromStringBinding(s, out b);
            if (r != 0) { sb.AppendLine(ep + ": bind=0x" + r.ToString("X8")); continue; }
            sb.AppendLine("--- " + ep + " ---");
            r = RpcMgmtIsServerListening(b);
            sb.AppendLine("  MgmtIsListening: 0x" + r.ToString("X8"));
            string n; r = RpcMgmtInqServerPrincName(b, 0, out n);
            if (r == 0) sb.AppendLine("  ServerPrincipalName: " + n);
            else sb.AppendLine("  ServerPrincipalName: 0x" + r.ToString("X8"));
            RpcBindingFree(ref b);
        }
        return sb.ToString();
    }
}
"@
Write-Output ([RpcMgmtTest]::Run())
