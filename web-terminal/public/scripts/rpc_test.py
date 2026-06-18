"""Direct RPC test via ctypes - attempt to call STDispatch's RPC interface"""
import ctypes
import ctypes.wintypes
import sys

# Load rpcrt4.dll
rpcrt4 = ctypes.WinDLL("rpcrt4.dll")

# RPC status code type
RPC_STATUS = ctypes.c_uint

# String binding
RpcBindingFromStringBindingW = rpcrt4.RpcBindingFromStringBindingW
RpcBindingFromStringBindingW.restype = RPC_STATUS
RpcBindingFromStringBindingW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_void_p)]

# Free binding
RpcBindingFree = rpcrt4.RpcBindingFree
RpcBindingFree.restype = RPC_STATUS
RpcBindingFree.argtypes = [ctypes.POINTER(ctypes.c_void_p)]

# Mgmt API
RpcMgmtIsServerListening = rpcrt4.RpcMgmtIsServerListening
RpcMgmtIsServerListening.restype = RPC_STATUS
RpcMgmtIsServerListening.argtypes = [ctypes.c_void_p]

# Try different endpoints
endpoints = [
    "ncalrpc:[ST.DispatchEvents]",
    "ncalrpc:[STDisp-EventSink]",
    "ncalrpc:[STDisp-FTQ]",
    "ncalrpc:[STN.Dispatch]",
    "ncalrpc:[STN.Core]",
    "ncalrpc:[STN.Core.Security]",
]

for ep in endpoints:
    binding = ctypes.c_void_p(0)
    status = RpcBindingFromStringBindingW(ep, ctypes.byref(binding))
    if status == 0:
        print(f"[+] {ep} -> BOUND (handle={hex(binding.value)})")
        # Try management API
        listen_status = RpcMgmtIsServerListening(binding)
        print(f"    MgmtIsServerListening: status={hex(listen_status)}")
        # Free
        RpcBindingFree(ctypes.byref(binding))
    else:
        print(f"[-] {ep} -> FAILED (status={hex(status)})")
