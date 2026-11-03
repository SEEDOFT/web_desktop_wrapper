from __future__ import annotations

import os
from pathlib import Path

SOURCE = r'''
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.WindowsRuntime;
using System.Threading.Tasks;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;

public static class WrapperImageShare {
    [ComImport, Guid("3A3DCD6C-3EAB-43DC-BCDE-45671CE800C8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IInterop {
        DataTransferManager GetForWindow(IntPtr hwnd, ref Guid iid);
        void ShowShareUIForWindow(IntPtr hwnd);
    }
    static DataTransferManager manager;
    static Windows.Foundation.TypedEventHandler<DataTransferManager, DataRequestedEventArgs> handler;
    public static async Task Open(IntPtr hwnd, string path) {
        var file = await StorageFile.GetFileFromPathAsync(path);
        var factory = (IInterop)WindowsRuntimeMarshal.GetActivationFactory(typeof(DataTransferManager));
        var iid = new Guid("A5CAEE9B-8708-49D1-8D36-67D25A8DA00C");
        if (manager != null) manager.DataRequested -= handler;
        manager = factory.GetForWindow(hwnd, ref iid);
        handler = (sender, args) => {
            args.Request.Data.Properties.Title = "Share image";
            args.Request.Data.SetStorageItems(new IStorageItem[] { file });
        };
        manager.DataRequested += handler;
        factory.ShowShareUIForWindow(hwnd);
    }
}
'''


def build_share_adapter(destination: Path) -> Path:
    """Compile at build time; installed apps do not need the Windows SDK."""
    import clr
    clr.AddReference("Microsoft.CSharp")
    from Microsoft.CSharp import CSharpCodeProvider
    from System import Array, String
    from System.CodeDom.Compiler import CompilerParameters

    sdk = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Kits/10/UnionMetadata"
    metadata = sorted(sdk.glob("10.*/Windows.winmd"))
    if not metadata:
        raise RuntimeError("Windows 10/11 SDK is required to build the native image sharing adapter.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    parameters = CompilerParameters()
    parameters.GenerateInMemory = False
    parameters.OutputAssembly = str(destination)
    for name in ("System", "System.Core", "System.Runtime", "System.Runtime.WindowsRuntime", "System.Runtime.InteropServices.WindowsRuntime"):
        parameters.ReferencedAssemblies.Add(clr.AddReference(name).Location)
    parameters.ReferencedAssemblies.Add(str(metadata[-1]))
    result = CSharpCodeProvider().CompileAssemblyFromSource(parameters, Array[String]([SOURCE]))
    if result.Errors.HasErrors:
        raise RuntimeError("Native image sharing adapter compilation failed: " + "; ".join(str(error) for error in result.Errors))
    return destination
