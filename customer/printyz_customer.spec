# PyInstaller spec for the PRINTYZ Clicker customer edition.
# Build:  pyinstaller customer/printyz_customer.spec --noconfirm  (run from the repository root)
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent
datas, binaries, hiddenimports = [], [], []
for pkg in ("printyz_clicker", "OCP", "build123d", "vtkmodules", "pyvista", "pyvistaqt", "manifold3d",
            "ocpsvg", "svgpathtools", "svgelements", "trimesh", "fontTools", "lib3mf", "ezdxf", "scooby"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += ["scipy.spatial", "scipy.sparse.csgraph", "matplotlib.backends.backend_agg"]

a = Analysis([str(ROOT / "customer" / "launch.py")], pathex=[str(ROOT / "src")], datas=datas,
             binaries=binaries, hiddenimports=hiddenimports,
             excludes=["tkinter", "pytest", "PyInstaller"], noarchive=False)
pyz = PYZ(a.pure)
icon = ROOT / "src" / "printyz_clicker" / "assets" / "printyz.ico"
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PRINTYZ Clicker", console=False,
          icon=str(icon) if icon.exists() else None)
coll = COLLECT(exe, a.binaries, a.datas, name="PRINTYZ Clicker")
