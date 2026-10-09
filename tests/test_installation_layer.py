# -*- coding: utf-8 -*-
"""Pure-Python mocks for the transactional package and persistent toolbar."""

from __future__ import annotations

import builtins
import hashlib
import importlib.util
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import sys
import tempfile
import types
from typing import Optional
import unittest
import uuid


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "contents" / "FBXTo3dsMax.files"
TOOLBAR = ROOT / "contents" / "f2m_toolbar.py"
PACKAGE_CONTENTS = ROOT / "PackageContents.xml"
REQUIRED_DESTINATIONS = {
    "PackageContents.xml",
    r"contents\LICENSE",
    r"contents\FBXTo3dsMax_Bootstrap.ms",
    r"contents\FBXTo3dsMax.files",
    r"contents\FBXTo3dsMax.version",
    r"contents\FBXTo3dsMax_UI.ms",
    r"contents\FBXTo3dsMax.mcr",
    r"contents\f2m_toolbar.py",
    r"contents\f2m_topology_transfer.py",
    r"contents\f2m_skin_replace.py",
    r"contents\f2m_smoothing.py",
    r"contents\f2m_fbx_metadata.py",
    r"contents\f2m_selfcheck.py",
    r"contents\FBXTo3dsMax_详细说明书.md",
    r"contents\tests\max_normals_safety.py",
    r"contents\f2m_test_fixtures.py",
}
MODULE_NAMES = {
    "f2m_fbx_metadata",
    "_f2m_fbx_metadata_runtime",
    "_fbx_to_3dsmax_toolbar_runtime",
    "_f2m_smoothing_runtime",
    "_f2m_sc_fbx_metadata_integrity",
    "_f2m_sc_fbx_metadata_runtime",
}
SELFCHECK_CONTROLLER_SLOT = "_FBXTO3DSMAX_SELFCHECK_CONTROLLER"


def _native(relative: str) -> Path:
    return Path(*PureWindowsPath(relative).parts)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _manifest_entries():
    entries = []
    destinations = set()
    for raw in MANIFEST.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.count("|") != 1:
            raise AssertionError("invalid manifest line: " + line)
        source, destination = (part.strip() for part in line.split("|", 1))
        if destination in destinations:
            raise AssertionError("duplicate destination: " + destination)
        source_path = ROOT / _native(source)
        if not source_path.is_file():
            raise AssertionError("missing manifest source: " + str(source_path))
        destinations.add(destination)
        entries.append((source, destination))
    if not entries:
        raise AssertionError("empty manifest")
    missing = REQUIRED_DESTINATIONS - destinations
    if missing:
        raise AssertionError("missing required destinations: " + repr(sorted(missing)))
    return entries


def _selfcheck_shutdown_code(maxscript_text: str) -> str:
    marker = (
        'python.Execute "import builtins\\n'
        "_f2m_controller = getattr(builtins, "
        "'_FBXTO3DSMAX_SELFCHECK_CONTROLLER', None)"
    )
    start = maxscript_text.find(marker)
    if start < 0:
        raise AssertionError("missing self-check shutdown Python block")
    payload_start = start + len('python.Execute "')
    end = maxscript_text.find(
        '" throwOnError:true clearUndoBuffer:false',
        payload_start,
    )
    if end < 0:
        raise AssertionError("unterminated self-check shutdown Python block")
    payload = maxscript_text[payload_start:end]
    return payload.replace("\\n", "\n")


class _PackageCycleMock:
    """Filesystem-only model of staging, hash verification and atomic switches."""

    def __init__(self, root: Path):
        self.root = root
        self.plugin_base = root / "ApplicationPlugins"
        self.work_root = root / "FBXTo3dsMaxInstaller"
        self.target = self.plugin_base / "FBXTo3dsMax"
        self.plugin_base.mkdir(parents=True)
        self.entries = _manifest_entries()

    def install(self) -> Optional[Path]:
        token = uuid.uuid4().hex
        stage = self.work_root / "Staging" / token / "FBXTo3dsMax"
        stage.mkdir(parents=True)
        records = []
        for source, destination in self.entries:
            source_path = ROOT / _native(source)
            destination_path = stage / _native(destination)
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination_path)
            source_hash = _sha256(source_path)
            if _sha256(destination_path) != source_hash:
                raise AssertionError("staging hash mismatch: " + destination)
            records.append((destination, source_hash))

        installed_manifest = (
            stage / "contents" / "FBXTo3dsMax.install-manifest.sha256"
        )
        installed_manifest.write_text(
            "".join(f"{destination}|{digest}\n" for destination, digest in records),
            encoding="utf-8",
        )

        backup = None
        if self.target.exists():
            backup = (
                self.work_root
                / "Backups"
                / ("1.4.24-" + token)
                / "FBXTo3dsMax"
            )
            backup.parent.mkdir(parents=True)
            self.target.rename(backup)
        stage.rename(self.target)

        for destination, digest in records:
            installed_path = self.target / _native(destination)
            if _sha256(installed_path) != digest:
                raise AssertionError("installed hash mismatch: " + destination)
        return backup

    def uninstall(self) -> Path:
        if not self.target.is_dir():
            raise AssertionError("package is not installed")
        archive = (
            self.work_root
            / "UninstallBackups"
            / uuid.uuid4().hex
            / "FBXTo3dsMax"
        )
        archive.parent.mkdir(parents=True)
        self.target.rename(archive)
        if self.target.exists() or not (archive / "PackageContents.xml").is_file():
            raise AssertionError("uninstall archive readback failed")
        return archive


class PackageContentsCompatibilityTests(unittest.TestCase):
    def test_max_2023_uses_the_required_post_startup_component_class(self):
        package_text = PACKAGE_CONTENTS.read_text(encoding="utf-8-sig")
        self.assertIn(
            '<Components Description="post-start-up scripts parts">',
            package_text,
        )
        self.assertNotIn(
            '<Components Description="启动后加载脚本">',
            package_text,
        )

    def test_every_production_python_execute_preserves_the_undo_buffer(self):
        for relative in (
            "contents/FBXTo3dsMax_UI.ms",
            "Install_FBXTo3dsMax.ms",
            "Uninstall_FBXTo3dsMax.ms",
            "contents/FBXTo3dsMax.mcr",
            "contents/FBXTo3dsMax_Bootstrap.ms",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8-sig")
            execute_lines = [
                (line_number, line)
                for line_number, line in enumerate(source.splitlines(), start=1)
                if "python.Execute" in line
                and not line.lstrip().startswith("--")
            ]
            self.assertTrue(execute_lines, relative)
            for line_number, line in execute_lines:
                self.assertIn(
                    "throwOnError:true",
                    line,
                    f"{relative}:{line_number}",
                )
                self.assertIn(
                    "clearUndoBuffer:false",
                    line,
                    f"{relative}:{line_number}",
                )


class _Signal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback

    def emit(self):
        if self.callback is not None:
            self.callback(False)


class _TimerSignal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback

    def disconnect(self, callback=None):
        if callback is None or callback is self.callback:
            self.callback = None

    def emit(self):
        callback = self.callback
        if callback is not None:
            callback()


class _Timer:
    pending = []

    def __init__(self):
        self.timeout = _TimerSignal()
        self.active = False
        self.deleted = False
        self.delay = None

    def setSingleShot(self, _value):
        pass

    def start(self, delay):
        self.delay = delay
        self.active = True
        self.pending.append(self)

    def stop(self):
        self.active = False

    def deleteLater(self):
        self.deleted = True

    def fire(self):
        if not self.active:
            return
        self.active = False
        self.timeout.emit()


class _SelfcheckController:
    def __init__(self, fail=False):
        self.fail = fail
        self.running = True
        self.shutdown_calls = 0

    def shutdown(self):
        self.shutdown_calls += 1
        if self.fail:
            raise RuntimeError("模拟停止失败")
        self.running = False

    def is_running(self):
        return self.running


class _Action:
    def __init__(self, parent):
        self.parent = parent
        self._object_name = ""
        self.deleted = False

    def setObjectName(self, value):
        self._object_name = value

    def objectName(self):
        return self._object_name

    def deleteLater(self):
        self.deleted = True


class _WidgetAction(_Action):
    def __init__(self, parent):
        super().__init__(parent)
        self.widget = None

    def setDefaultWidget(self, widget):
        self.widget = widget


class _Point:
    def __init__(self, x=0, y=0):
        self._x = int(x)
        self._y = int(y)

    def x(self):
        return self._x

    def y(self):
        return self._y


class _Size:
    def __init__(self, width, height):
        self._width = int(width)
        self._height = int(height)

    def width(self):
        return self._width

    def height(self):
        return self._height


class _Rect:
    def __init__(self, point, size):
        self._x = point.x()
        self._y = point.y()
        self._width = size.width()
        self._height = size.height()

    def x(self):
        return self._x

    def y(self):
        return self._y

    def width(self):
        return self._width

    def height(self):
        return self._height

    def top(self):
        return self._y

    def center(self):
        return _Point(self._x + self._width // 2, self._y + self._height // 2)

    def contains(self, point):
        return (
            self._x <= point.x() < self._x + self._width
            and self._y <= point.y() < self._y + self._height
        )

    def intersects(self, other):
        return not (
            self._x + self._width <= other._x
            or other._x + other._width <= self._x
            or self._y + self._height <= other._y
            or other._y + other._height <= self._y
        )


class _Icon:
    def __init__(self, path):
        self.path = path

    def isNull(self):
        return not bool(self.path)


class _ToolButton:
    active_button = None

    def __init__(self, parent):
        self.parent = parent
        self._object_name = ""
        self._text = ""
        self._icon = _Icon("")
        self._width = 0
        self._height = 0
        self.clicked = _Signal()
        self.deleted = False
        self.polished = False
        self.preferred_size = _Size(156, 38)
        self.minimum_hint = _Size(148, 36)
        self.geometry_updates = 0

    def setObjectName(self, value):
        self._object_name = value

    def objectName(self):
        return self._object_name

    def setText(self, value):
        self._text = value

    def text(self):
        return self._text

    def setToolTip(self, _value):
        pass

    def setStatusTip(self, _value):
        pass

    def setIcon(self, value):
        self._icon = value

    def icon(self):
        return self._icon

    def setIconSize(self, _value):
        pass

    def setToolButtonStyle(self, _value):
        pass

    def setAutoRaise(self, _value):
        pass

    def setMinimumSize(self, value):
        self._width = value.width()
        self._height = value.height()

    def setAccessibleName(self, _value):
        pass

    def setStyleSheet(self, _value):
        self.style_sheet = _value
        self.polished = False

    def ensurePolished(self):
        self.polished = True

    def sizeHint(self):
        if not self.polished:
            raise RuntimeError("Unpolished mock cannot provide the styled size")
        return self.preferred_size

    def minimumSizeHint(self):
        if not self.polished:
            raise RuntimeError("Unpolished mock cannot provide the styled minimum")
        return self.minimum_hint

    def updateGeometry(self):
        self.geometry_updates += 1

    def width(self):
        return self._width

    def height(self):
        return self._height

    def size(self):
        return _Size(self._width, self._height)

    def mapToGlobal(self, point):
        return _Point(520 + point.x(), 18 + point.y())

    def isVisibleTo(self, _ancestor):
        return bool(self.parent.visible and not self.deleted)

    def isEnabled(self):
        return True

    def isAncestorOf(self, _other):
        return False

    def deleteLater(self):
        self.deleted = True


class _ToolBar:
    def __init__(self, title, parent):
        self.title = title
        self.parent = parent
        self._object_name = ""
        self._actions = []
        self.visible = False
        self.deleted = False
        self._minimum_width = 0

    def setObjectName(self, value):
        self._object_name = value

    def objectName(self):
        return self._object_name

    def setWindowTitle(self, value):
        self.title = value

    def setMovable(self, _value):
        pass

    def setFloatable(self, _value):
        pass

    def setAllowedAreas(self, _value):
        pass

    def actions(self):
        return list(self._actions)

    def removeAction(self, action):
        self._actions.remove(action)

    def addAction(self, action):
        self._actions.append(action)
        if getattr(action, "widget", None) is not None:
            _ToolButton.active_button = action.widget

    def widgetForAction(self, action):
        return getattr(action, "widget", None)

    def setIconSize(self, _value):
        pass

    def setMinimumWidth(self, value):
        self._minimum_width = value

    def show(self):
        self.visible = True

    def raise_(self):
        pass

    def hide(self):
        self.visible = False

    def setParent(self, value):
        self.parent = value

    def deleteLater(self):
        self.deleted = True

    def isVisible(self):
        return self.visible


class _MainWindow:
    def __init__(self):
        self.toolbars = []
        self.areas = {}

    def findChildren(self, _kind):
        return list(self.toolbars)

    def addToolBar(self, area, toolbar):
        if toolbar not in self.toolbars:
            self.toolbars.append(toolbar)
        self.areas[toolbar] = area

    def removeToolBar(self, toolbar):
        if toolbar in self.toolbars:
            self.toolbars.remove(toolbar)
        self.areas.pop(toolbar, None)

    def toolBarArea(self, toolbar):
        return self.areas.get(toolbar)

    def mapToGlobal(self, point):
        return point

    def size(self):
        return _Size(1920, 1080)


class _Application:
    active_modal = None

    @staticmethod
    def processEvents():
        return None

    @staticmethod
    def activeModalWidget():
        return _Application.active_modal

    @staticmethod
    def widgetAt(_point):
        return _ToolButton.active_button


class _Screen:
    @staticmethod
    def availableGeometry():
        return _Rect(_Point(0, 0), _Size(1920, 1080))


class _GuiApplication:
    @staticmethod
    def screenAt(_point):
        return _Screen()


class InstallationLayerTests(unittest.TestCase):
    def test_both_installer_required_lists_are_literal_manifest_subsets(self):
        entries = _manifest_entries()
        manifest = {PureWindowsPath(target).as_posix().casefold()
                    for _source, target in entries}
        self.assertEqual(len(manifest), 32)
        native = (ROOT / "Install_FBXTo3dsMax.ms").read_text("utf-8-sig")
        powershell = (ROOT / "tools/Install_FBXTo3dsMax.ps1").read_text("utf-8-sig")
        patterns = (
            (native, r"local\s+requiredManifestDestinations\s*=\s*#\((.*?)\)\s*for\s+requiredDestination\b", r'"((?:\\.|[^"\\])*)"', True),
            (powershell, r"foreach\s*\(\s*\$requiredDestination\s+in\s+@\((.*?)\)\s*\)", r'"([^"\r\n]*)"', False),
        )
        required_sets = []
        for source, pattern, literal, escaped in patterns:
            blocks = re.findall(pattern, source, re.DOTALL)
            self.assertEqual(len(blocks), 1)
            self.assertIsNone(re.search(r"[^,\s]", re.sub(literal, "", blocks[0])))
            values = re.findall(literal, blocks[0])
            normalized = [PureWindowsPath(value.replace("\\\\", "\\")
                          if escaped else value).as_posix().casefold() for value in values]
            self.assertTrue(normalized)
            self.assertEqual(len(normalized), len(set(normalized)))
            required = set(normalized)
            self.assertFalse(required - manifest, sorted(required - manifest))
            for target in required:
                self.assertNotIn(PureWindowsPath(target).suffix, (".fbx", ".max", ".blend"))
            for target in ("contents/f2m_test_fixtures.py", "contents/f2m_i18n.py",
                           "contents/f2m_report_i18n.py", "contents/license"):
                self.assertIn(target, required)
            required_sets.append(required)
        self.assertEqual(required_sets[0], required_sets[1])

    def test_native_installer_requirements_match_the_public_source_manifest(self):
        installer = (ROOT / "Install_FBXTo3dsMax.ms").read_text(
            encoding="utf-8-sig"
        )
        required_array = re.search(
            r"local\s+requiredManifestDestinations\s*=\s*#\((.*?)\)"
            r"\s*for\s+requiredDestination\b",
            installer,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(
            required_array, "native installer required-target array is missing"
        )
        literals = re.findall(r'"((?:\\.|[^"\\])*)"', required_array.group(1))
        remainder = re.sub(r'"((?:\\.|[^"\\])*)"', "", required_array.group(1))
        self.assertIsNone(
            re.search(r"[^,\s]", remainder),
            "native installer requirements must be literal strings, not expressions",
        )
        required = {
            PureWindowsPath(value.replace("\\\\", "\\")).as_posix().casefold()
            for value in literals
        }
        self.assertTrue(required, "native installer required-target array is empty")
        self.assertIn("contents/f2m_test_fixtures.py", required)
        self.assertIn("contents/license", required)
        for target in required:
            with self.subTest(required_target=target):
                path = PureWindowsPath(target)
                self.assertNotIn("fixtures", path.parts)
                self.assertNotEqual(path.suffix, ".fbx")

        entries = _manifest_entries()
        self.assertEqual(len(entries), 32)
        manifest_targets = {
            PureWindowsPath(destination).as_posix().casefold()
            for _source, destination in entries
        }
        self.assertFalse(
            required - manifest_targets,
            "native installer requires targets absent from the fixed manifest: "
            + repr(sorted(required - manifest_targets)),
        )

    def test_manifest_and_transaction_cycle(self):
        entries = _manifest_entries()
        self.assertEqual(len(entries), 32)
        with tempfile.TemporaryDirectory(prefix="FBXTo3dsMax-install-mock-") as temp:
            package = _PackageCycleMock(Path(temp))

            self.assertIsNone(package.install())
            stale = package.target / "contents" / "stale-from-old-version.py"
            stale.write_text("stale", encoding="utf-8")

            backup = package.install()
            self.assertIsNotNone(backup)
            self.assertTrue(backup.is_dir())
            self.assertFalse(stale.exists())
            first_archive = package.uninstall()
            self.assertTrue(first_archive.is_dir())

            self.assertIsNone(package.install())
            second_archive = package.uninstall()
            self.assertTrue(second_archive.is_dir())
            self.assertNotEqual(first_archive, second_archive)
            self.assertFalse(package.target.exists())

    def test_installer_and_uninstaller_share_exclusive_package_lock(self):
        sources = {}
        for relative in (
            "Install_FBXTo3dsMax.ms",
            "Uninstall_FBXTo3dsMax.ms",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8-sig")
            sources[relative] = text
            self.assertIn('joinPath workRoot "Locks"', text, relative)
            self.assertIn('"package.lock"', text, relative)
            self.assertIn(
                'dotNetClass "System.IO.FileShare"',
                text,
                relative,
            )
            self.assertIn(
                "fileClass.Open lockPath fileMode.OpenOrCreate "
                "fileAccess.ReadWrite fileShare.None",
                text,
                relative,
            )
            self.assertEqual(
                text.count("acquirePackageMutationLock workRoot"),
                2,
                relative,
            )
            self.assertEqual(
                text.count("releasePackageMutationLock()"),
                1,
                relative,
            )
            self.assertLess(
                text.rindex("acquirePackageMutationLock workRoot"),
                text.rindex("removeLiveRuntime()"),
                relative,
            )
            self.assertLess(
                text.rindex("releasePackageMutationLock()"),
                text.rindex("messageBox finalDialogText"),
                relative,
            )
        self.assertIn(
            "无法完整清理旧版运行模块，覆盖安装已取消",
            sources["Install_FBXTo3dsMax.ms"],
        )
        self.assertIn(
            "仍将继续恢复磁盘状态",
            sources["Install_FBXTo3dsMax.ms"],
        )
        self.assertIn(
            "runtimeCleanupAttempted = true",
            sources["Install_FBXTo3dsMax.ms"],
        )
        self.assertIn(
            "runtimeCleanupAttempted = true",
            sources["Uninstall_FBXTo3dsMax.ms"],
        )
        self.assertIn(
            "无法完整清理插件运行模块，卸载已取消",
            sources["Uninstall_FBXTo3dsMax.ms"],
        )

    def test_installer_failure_rollback_is_ordered_and_readback_verified(self):
        installer = (ROOT / "Install_FBXTo3dsMax.ms").read_text(
            encoding="utf-8-sig"
        )

        package_contract = installer[
            installer.index("fn snapshotPreviousPackage") :
            installer.index("fn snapshotManagedFile")
        ]
        self.assertIn("directoryClass.GetFiles", package_contract)
        self.assertIn("previousPackageRecords", package_contract)
        self.assertIn("sha256File absolutePath", package_contract)
        self.assertIn("fileClass.Exists livePath", package_contract)
        self.assertIn("sha256File livePath != record[2]", package_contract)
        self.assertIn("packageOwnershipTokens", package_contract)
        self.assertIn("liveFiles.count != previousPackageRecords.count", package_contract)

        managed_contract = installer[
            installer.index("fn verifyManagedFiles") :
            installer.index("fn archiveOwnedLegacyFile")
        ]
        self.assertIn("local allOk = true", managed_contract)
        self.assertIn("sha256File originalPath != originalHash", managed_contract)
        self.assertIn(
            "textContainsAll originalPath ownershipTokens",
            managed_contract,
        )
        self.assertIn("sha256File snapshotPath != originalHash", managed_contract)
        self.assertIn("sha256File regeneratedPath != currentHash", managed_contract)
        self.assertIn(
            "textContainsAll regeneratedPath ownershipTokens",
            managed_contract,
        )
        self.assertIn("verifyManagedFiles()", managed_contract)
        self.assertIn("recordRollbackFailure", managed_contract)
        self.assertIn("previousBootstrapPreservesManagedFiles", managed_contract)

        legacy_contract = installer[
            installer.index("fn verifyLegacyMoves") :
            installer.index("fn restorePreviousPackageState")
        ]
        self.assertIn("legacyMoves[i][4]", legacy_contract)
        self.assertIn("sha256File originalPath != expectedHash", legacy_contract)
        self.assertIn(
            "textContainsAll originalPath ownershipTokens",
            legacy_contract,
        )
        self.assertIn("fileClass.Exists archivePath", legacy_contract)
        self.assertIn("verifyLegacyMoves()", legacy_contract)
        self.assertIn("recordRollbackFailure", legacy_contract)
        self.assertIn(
            "append legacyMoves #(originalPath, archivePath, beforeHash, tokens)",
            installer,
        )

        rollback = installer[
            installer.index("local installError = getCurrentException()") :
            installer.index("-- 文件锁在任何结果对话框之前释放")
        ]
        self.assertNotRegex(
            rollback,
            r"\bthrow\b",
            "外层 catch 必须用本地错误状态完成回滚，不能再触发 MAXScript 的参数化 throw 解析限制。",
        )
        self.assertIn('local failedPackageError = ""', rollback)
        self.assertIn(
            'failedPackageError = "失败的新插件包移出后的存在性读回失败。"',
            rollback,
        )
        self.assertIn(
            'failedPackageError = "失败的新插件包移出后的归属标记读回失败。"',
            rollback,
        )
        self.assertIn(
            'recordRollbackFailure ("无法完整移出失败的新插件包：" + failedPackageError)',
            rollback,
        )
        package_restore = rollback.index(
            "restorePreviousPackageState targetPackage packageBackup"
        )
        legacy_restore = rollback.index("restoreLegacyMoves()")
        managed_restore = rollback.index("restoreManagedFiles")
        bootstrap_restart = rollback.index(
            "restartPreviousBootstrap targetPackage"
        )
        self.assertLess(package_restore, legacy_restore)
        self.assertLess(legacy_restore, managed_restore)
        self.assertLess(managed_restore, bootstrap_restart)
        self.assertIn("previousBootstrapPreservesManagedFiles", rollback)
        self.assertIn("verifyPreviousPackageSnapshot targetPackage", rollback)
        self.assertIn("verifyLegacyMoves()", rollback)
        self.assertIn("verifyManagedFiles()", rollback)
        self.assertIn("rollbackFailures.count == 0", rollback)
        self.assertIn("回滚最终状态：不完整", rollback)
        self.assertIn("安装失败（回滚不完整）", rollback)
        self.assertIn("安装失败，而且回滚不完整", rollback)
        self.assertIn("未恢复项目：", rollback)
        self.assertNotIn("警告：无法恢复旧插件包", installer)
        self.assertNotIn("警告：无法恢复受管文件", installer)

    def test_interactive_install_verifiers_are_child_process_only(self):
        harness = (
            ROOT / "tests" / "max_install_v1319_harness.ms"
        ).read_text(encoding="utf-8-sig")
        self.assertIn("F2M_INSTALL_HARNESS_TOKEN", harness)
        self.assertIn("environmentClass.GetCommandLineArgs()", harness)
        self.assertIn("validRunToken runToken", harness)
        self.assertIn("dedicatedHarnessCommand commandArgs", harness)
        self.assertIn('"maxscript"', harness)
        self.assertIn("sameFullPath sourceHarnessName expectedHarnessPath", harness)
        self.assertIn("getSourceFileName()", harness)
        self.assertIn(
            'pathClass.Combine workspaceRoot "Install_FBXTo3dsMax.ms"',
            harness,
        )
        self.assertNotRegex(
            harness,
            r"(?im)[a-z]:[\\/]+(?:ai[\\/]+codex|users[\\/]+)",
        )
        self.assertIn("STARTED", harness)
        self.assertIn("for passIndex = 1 to 2", harness)
        self.assertIn("requireSuccessfulInstall passIndex", harness)
        self.assertIn("F2M_Installer_RunStatus != 1", harness)
        self.assertIn(
            'F2M_Installer_FinalDialogTitle != "FBXTo3dsMax"',
            harness,
        )
        self.assertIn("F2M_Installer_FinalDialogText", harness)
        self.assertIn("FBXTo3dsMax v1.4.24 安装成功。", harness)
        self.assertIn("中文结果载荷=通过", harness)
        self.assertIn("F2M_STALE_TOPOLOGY_SENTINEL", harness)
        self.assertIn("F2M_STALE_SKIN_SENTINEL", harness)
        self.assertIn("F2M_STALE_ALIAS_SENTINEL", harness)
        self.assertIn("Helper缓存清理=通过", harness)
        self.assertIn("expectedManifestCount = 32", harness)
        self.assertIn("安装清单=32/32", harness)
        self.assertIn("quitMax #noPrompt", harness)

        wrapper = (
            ROOT / "tests" / "max_installed_interactive_verify_and_quit.py"
        ).read_text(encoding="utf-8-sig")
        self.assertIn('TOKEN_ENV = "F2M_INSTALLED_VERIFY_TOKEN"', wrapper)
        self.assertIn("_process_command_line_args()", wrapper)
        self.assertIn("_has_exact_python_host_identity", wrapper)
        self.assertIn('args[index + 1].lower() == "pythonhost"', wrapper)
        self.assertIn(
            're.fullmatch(r"v1\\.4\\.24-[0-9a-fA-F]{32}", run_token)',
            wrapper,
        )
        self.assertNotIn("v1\\.3\\.19-", wrapper)
        self.assertIn('"state": "started"', wrapper)
        self.assertIn('rt.quitMax(rt.Name("noPrompt"))', wrapper)

        verifier = (
            ROOT / "tests" / "max_installed_interactive_verify.py"
        ).read_text(encoding="utf-8-sig")
        self.assertIn('EXPECTED_VERSION = "1.4.24"', verifier)
        self.assertIn("FBXTo3dsMax.version", verifier)
        self.assertIn("installed_version = _read_installed_version()", verifier)
        self.assertNotIn('"version": "1.4.24"', verifier)

        for runner_name, token_name in (
            ("run_install_v1319_harness.ps1", "F2M_INSTALL_HARNESS_TOKEN"),
            ("run_installed_verify_v1319.ps1", "F2M_INSTALLED_VERIFY_TOKEN"),
        ):
            runner = (ROOT / "tests" / runner_name).read_text(
                encoding="utf-8-sig"
            )
            self.assertIn(token_name, runner, runner_name)
            self.assertIn("$process.Id", runner, runner_name)
            self.assertIn("$runToken", runner, runner_name)
            self.assertIn("$process.ExitCode", runner, runner_name)
            self.assertIn(
                "Get-Process -Name @('3dsmax', '3dsmaxbatch')",
                runner,
                runner_name,
            )
            if runner_name == "run_installed_verify_v1319.ps1":
                self.assertIn(
                    "$result.version -ne '1.4.24'",
                    runner,
                    runner_name,
                )

    def test_runtime_cleanup_lists_include_metadata_aliases(self):
        for relative in (
            "Install_FBXTo3dsMax.ms",
            "Uninstall_FBXTo3dsMax.ms",
            os.path.join("contents", "FBXTo3dsMax.mcr"),
        ):
            text = (ROOT / relative).read_text(encoding="utf-8-sig")
            for name in MODULE_NAMES:
                self.assertIn(name, text, f"{relative} is missing {name}")
        installer = (ROOT / "Install_FBXTo3dsMax.ms").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn('dotNetObject "System.Text.UTF8Encoding" false', installer)
        self.assertIn(
            "fileClass.WriteAllText installedHashManifest",
            installer,
        )
        self.assertNotIn(
            "createFile installedHashManifest",
            installer,
        )
        self.assertNotIn("fn log message", installer)
        bootstrap = (
            ROOT / "contents" / "FBXTo3dsMax_Bootstrap.ms"
        ).read_text(encoding="utf-8-sig")
        self.assertNotIn("fn log message", bootstrap)
        for relative in (
            "Install_FBXTo3dsMax.ms",
            "Uninstall_FBXTo3dsMax.ms",
        ):
            cleanup = (ROOT / relative).read_text(encoding="utf-8-sig")
            self.assertIn("F2M_TopologyHelper = undefined", cleanup)
            self.assertIn("F2M_SkinHelper = undefined", cleanup)
            self.assertIn("F2M_Helper = undefined", cleanup)
            self.assertIn("无法清除旧版 MAXScript Helper 缓存", cleanup)

    def test_overwrite_and_uninstall_stop_selfcheck_before_module_eviction(self):
        had_previous = hasattr(builtins, SELFCHECK_CONTROLLER_SLOT)
        previous = getattr(builtins, SELFCHECK_CONTROLLER_SLOT, None)
        try:
            for relative in (
                "Install_FBXTo3dsMax.ms",
                "Uninstall_FBXTo3dsMax.ms",
            ):
                text = (ROOT / relative).read_text(encoding="utf-8-sig")
                controller_index = text.index(SELFCHECK_CONTROLLER_SLOT)
                module_eviction_index = text.index(
                    "for _f2m_name in _f2m_known_modules"
                )
                self.assertLess(controller_index, module_eviction_index)
                self.assertIn("自检子进程在停止后仍然运行", text)
                self.assertIn("throwOnError:true", text[controller_index:])

                shutdown_code = _selfcheck_shutdown_code(text)
                controller = _SelfcheckController()
                setattr(builtins, SELFCHECK_CONTROLLER_SLOT, controller)
                exec(shutdown_code, {})
                self.assertEqual(controller.shutdown_calls, 1)
                self.assertFalse(controller.running)
                self.assertFalse(
                    hasattr(builtins, SELFCHECK_CONTROLLER_SLOT),
                    relative,
                )

                failing = _SelfcheckController(fail=True)
                setattr(builtins, SELFCHECK_CONTROLLER_SLOT, failing)
                with self.assertRaisesRegex(RuntimeError, "模拟停止失败"):
                    exec(shutdown_code, {})
                self.assertEqual(failing.shutdown_calls, 1)
                self.assertIs(
                    getattr(builtins, SELFCHECK_CONTROLLER_SLOT),
                    failing,
                    relative,
                )

            installer = (ROOT / "Install_FBXTo3dsMax.ms").read_text(
                encoding="utf-8-sig"
            )
            self.assertIn("覆盖安装已阻止", installer)
            uninstaller = (ROOT / "Uninstall_FBXTo3dsMax.ms").read_text(
                encoding="utf-8-sig"
            )
            self.assertIn("卸载已阻止", uninstaller)
        finally:
            if had_previous:
                setattr(builtins, SELFCHECK_CONTROLLER_SLOT, previous)
            elif hasattr(builtins, SELFCHECK_CONTROLLER_SLOT):
                delattr(builtins, SELFCHECK_CONTROLLER_SLOT)

    def test_toolbar_host_timing_callbacks_and_chinese_install_ui(self):
        toolbar = TOOLBAR.read_text(encoding="utf-8-sig")
        self.assertIn("SCRIPT_FILE = os.path.abspath(__file__)", toolbar)
        self.assertIn('MAIN_TOOLBAR_OBJECT_NAME = "Main Toolbar"', toolbar)
        self.assertIn('BUTTON_TEXT = "FBX 转 MAX"', toolbar)
        self.assertIn("def install_and_schedule", toolbar)
        self.assertNotIn("singleShot(0, install)", toolbar)
        self.assertNotIn("QTimer.singleShot", toolbar)
        self.assertIn("def _cancel_scheduled_installs", toolbar)
        self.assertIn("def begin_shutdown", toolbar)
        self.assertIn("def cancel_shutdown", toolbar)

        bootstrap = (
            ROOT / "contents" / "FBXTo3dsMax_Bootstrap.ms"
        ).read_text(encoding="utf-8-sig")
        for callback in (
            "#preWorkspaceChange",
            "#postWorkspaceChange",
            "#preLoadingCuiToolbars",
            "#postLoadingCuiToolbars",
            "#preSavingCuiToolbars",
            "#postSavingCuiToolbars",
            "#systemShutdownCheck",
            "#systemShutdownCheckFailed",
            "#systemShutdownCheckPassed",
            "#preSystemShutdown",
            "#welcomeScreenDone",
        ):
            self.assertIn(callback, bootstrap)
        self.assertIn(
            "#postSavingCuiToolbars "
            '"try(::FBXTo3dsMax_Bootstrap.restoreToolbarAfterCui())catch()"',
            bootstrap,
        )
        self.assertIn("if shutdownInProgress do return true", bootstrap)
        self.assertIn("当前 3ds Max 不支持欢迎界面完成回调", bootstrap)
        self.assertIn("spec_from_file_location", bootstrap)
        self.assertIn("_fbx_to_3dsmax_toolbar_runtime", bootstrap)
        self.assertIn("_F2M_IMPORT_COMPLETE", bootstrap)
        self.assertIn(
            "if sys.modules.get(_f2m_toolbar_name) is _f2m_toolbar_module:",
            bootstrap,
        )
        self.assertNotIn(
            "python.Execute pythonCode fileName:toolbarScript",
            bootstrap,
        )
        self.assertIn(
            'systemTools.getEnvVariable "F2M_SELFCHECK_CHILD"',
            bootstrap,
        )
        self.assertIn("sysInfo.getCommandLineArgs()", bootstrap)
        self.assertIn('== "-batch"', bootstrap)
        self.assertIn("批处理进程已跳过顶部按钮初始化", bootstrap)

        installer = (ROOT / "Install_FBXTo3dsMax.ms").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("global F2M_Installer_RunStatus", installer)
        self.assertIn("F2M_Installer_RunStatus = -1", installer)
        self.assertIn("F2M_Installer_RunStatus = 1", installer)
        self.assertGreaterEqual(
            installer.count("F2M_Installer_RunStatus = 0"),
            2,
        )
        self.assertIn("verifyToolbar()", installer)
        self.assertIn("安装成功", installer)
        self.assertIn("installed successfully", installer)
        self.assertIn('fn localized chineseText englishText', installer)
        self.assertIn('if displayEnglish then englishText else chineseText', installer)
        self.assertIn('selectedLanguage == "en"', installer)
        self.assertIn('localized "FBXTo3dsMax - 安装失败" "FBXTo3dsMax - Installation failed"', installer)

        uninstaller = (ROOT / "Uninstall_FBXTo3dsMax.ms").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("FBXTo3dsMax - 卸载完成", uninstaller)
        self.assertIn('localized "FBXTo3dsMax - 卸载失败" "FBXTo3dsMax - Uninstall failed"', uninstaller)
        self.assertIn('if displayEnglish then englishText else chineseText', uninstaller)
        self.assertIn('.rollback-generated"', uninstaller)
        self.assertIn(
            "fileClass.Move originalPath regeneratedPath",
            uninstaller,
        )
        self.assertIn(
            "fileClass.Move archivePath originalPath",
            uninstaller,
        )

        macro = (ROOT / "contents" / "FBXTo3dsMax.mcr").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn('toolTip:"FBXTo3dsMax"', macro)
        self.assertIn("localizedMessage", macro)
        self.assertIn("m.translate", macro)

    def _toolbar_sizing_namespace(self):
        import ast

        source = TOOLBAR.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        functions = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in ("_fit_button_size", "refresh_language")
        ]
        namespace = {"QtCore": types.SimpleNamespace(QSize=_Size)}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(TOOLBAR), "exec"), namespace)
        return namespace

    def test_toolbar_minimum_uses_polished_style_hints_and_keeps_floor(self):
        namespace = self._toolbar_sizing_namespace()
        button = _ToolButton(None)
        # Hints stand for current font/icon/padding; their values are supplied by Qt.
        cases = (
            ((180, 45), (180, 45), (180, 45)),
            ((236, 51), (214, 56), (236, 56)),
            ((96, 27), (101, 29), (118, 34)),
        )
        for preferred, minimum, expected in cases:
            with self.subTest(preferred=preferred, minimum=minimum):
                button.preferred_size = _Size(*preferred)
                button.minimum_hint = _Size(*minimum)
                button.setStyleSheet("changed actual style")
                namespace["_fit_button_size"](button)
                self.assertTrue(button.polished)
                self.assertEqual((button.width(), button.height()), expected)
        self.assertEqual(button.geometry_updates, len(cases))

    def test_toolbar_creation_measures_after_text_icon_and_stylesheet(self):
        import ast

        namespace = self._toolbar_sizing_namespace()
        tree = ast.parse(TOOLBAR.read_text(encoding="utf-8-sig"))
        manager = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "_ToolbarManager")
        factory = next(node for node in manager.body if isinstance(node, ast.FunctionDef) and node.name == "_make_button_action")
        test = self

        class StyledButton(_ToolButton):
            def ensurePolished(self):
                test.assertEqual(self.text(), "FBX 转 MAX")
                test.assertFalse(self.icon().isNull())
                test.assertIn("font-weight: 600", self.style_sheet)
                super().ensurePolished()

        namespace.update(
            QtWidgets=types.SimpleNamespace(QWidgetAction=_WidgetAction, QToolButton=StyledButton),
            ACTION_OBJECT_NAME="FBXTo3dsMax.OpenWidgetAction", BUTTON_OBJECT_NAME="FBXTo3dsMax.TopButton",
            BUTTON_TEXT="FBX 转 MAX", BUTTON_TOOLTIP="打开 FBXTo3dsMax",
            _t=lambda value: value, _text_beside_icon=lambda: "text-beside-icon", _run_macro=lambda _checked=False: None,
        )
        exec(compile(ast.Module(body=[factory], type_ignores=[]), str(TOOLBAR), "exec"), namespace)
        action, button = namespace["_make_button_action"](None, None, _Icon("actual-icon"))
        self.assertIs(action.widget, button)
        self.assertEqual((button.width(), button.height()), (156, 38))
        self.assertEqual(button.geometry_updates, 1)

    def test_toolbar_language_refresh_remeasures_same_button_action_and_timers(self):
        namespace = self._toolbar_sizing_namespace()
        button = _ToolButton(None)
        action = object()
        timers = [object(), object(), object()]
        manager = types.SimpleNamespace(
            shutting_down=False, button=button, widget_action=action,
            _retry_timers=timers, fallback_toolbar=None,
        )
        locale = ["zh-CN"]
        api = {}
        namespace.update(
            _manager=manager, BUTTON_TEXT="FBX 转 MAX", BUTTON_TOOLTIP="打开 FBXTo3dsMax",
            API_SLOT="test_toolbar_api", builtins=types.SimpleNamespace(test_toolbar_api=api),
            _t=lambda value: {"FBX 转 MAX": "FBX to MAX", "打开 FBXTo3dsMax": "Open FBXTo3dsMax"}.get(value, value)
            if locale[0] == "en" else value,
            _language_module=lambda: types.SimpleNamespace(get_language=lambda: locale[0]),
        )
        for language, hint, expected_text in (
            ("zh-CN", (180, 45), "FBX 转 MAX"),
            ("en", (222, 48), "FBX to MAX"),
            ("zh-CN", (180, 45), "FBX 转 MAX"),
        ):
            locale[0] = language
            button.preferred_size = _Size(*hint)
            button.minimum_hint = _Size(*hint)
            self.assertTrue(namespace["refresh_language"]())
            self.assertEqual(button.text(), expected_text)
            self.assertEqual((button.width(), button.height()), hint)
            self.assertEqual(api["language"], language)
            self.assertIs(manager.button, button)
            self.assertIs(manager.widget_action, action)
            self.assertIs(manager._retry_timers, timers)
        self.assertEqual(button.geometry_updates, 3)

    def test_toolbar_shutdown_refresh_does_not_touch_button_size(self):
        namespace = self._toolbar_sizing_namespace()
        button = _ToolButton(None)
        namespace.update(
            _manager=types.SimpleNamespace(shutting_down=True, button=button, fallback_toolbar=None),
            BUTTON_TEXT="FBX 转 MAX", BUTTON_TOOLTIP="打开 FBXTo3dsMax",
            API_SLOT="test_toolbar_api", builtins=types.SimpleNamespace(),
        )
        self.assertTrue(namespace["refresh_language"]())
        self.assertFalse(button.polished)
        self.assertEqual(button.geometry_updates, 0)

    def _toolbar_install_layout_case(self, second_main_fails=False,
                                     fallback_fails=False):
        import ast

        # Execute the actual manager and verifier with existing Qt substitutes.
        tree = ast.parse(TOOLBAR.read_text(encoding="utf-8-sig"))
        selected = [node for node in tree.body
                    if (isinstance(node, ast.ClassDef)
                        and node.name == "_ToolbarManager")
                    or (isinstance(node, ast.FunctionDef)
                        and node.name in ("_fit_button_size", "_global_rect",
                                          "_delete_qobject"))]
        main = _MainWindow()
        main_toolbar = _ToolBar("Main", main)
        main_toolbar.setObjectName("Main Toolbar")
        main_toolbar.show()
        main.addToolBar("top", main_toolbar)
        previous_fallback = _ToolBar("Previous fallback", main)
        previous_fallback.setObjectName("FBXTo3dsMax.FallbackToolbar")
        previous_fallback.show()
        main.addToolBar("top", previous_fallback)
        events, created, verified = [], [], []
        previous_active = _ToolButton.active_button
        self.addCleanup(setattr, _ToolButton, "active_button", previous_active)

        class LayoutApplication(_Application):
            @staticmethod
            def processEvents():
                events.append(len(events) + 1)
                # Model a real layout change after the first successful verify.
                if len(events) == 2 and second_main_fails:
                    main_toolbar.hide()
                if len(events) == 3 and fallback_fails:
                    for toolbar in main.toolbars:
                        if toolbar.objectName() == "FBXTo3dsMax.FallbackToolbar":
                            toolbar.hide()

        namespace = {
            "os": os, "ICON_PATH": str(ROOT / "contents/icons/FBXTo3dsMax.svg"),
            "qtmax": types.SimpleNamespace(GetQMaxMainWindow=lambda: main),
            "QtCore": types.SimpleNamespace(QSize=_Size, QPoint=_Point, QRect=_Rect),
            "QtGui": types.SimpleNamespace(QIcon=_Icon,
                                            QGuiApplication=_GuiApplication),
            "QtWidgets": types.SimpleNamespace(QToolBar=_ToolBar,
                QToolButton=_ToolButton, QWidgetAction=_WidgetAction,
                QApplication=LayoutApplication),
            "MAIN_TOOLBAR_OBJECT_NAME": "Main Toolbar",
            "LEGACY_TOOLBAR_OBJECT_NAME": "FBXTo3dsMax.Toolbar",
            "FALLBACK_TOOLBAR_OBJECT_NAME": "FBXTo3dsMax.FallbackToolbar",
            "ACTION_OBJECT_NAME": "FBXTo3dsMax.OpenWidgetAction",
            "BUTTON_OBJECT_NAME": "FBXTo3dsMax.TopButton",
            "BUTTON_TEXT": "FBX 转 MAX", "BUTTON_TOOLTIP": "打开 FBXTo3dsMax",
            "_t": lambda value: value, "_top_toolbar_area": lambda: "top",
            "_text_beside_icon": lambda: "text-beside-icon",
            "_run_macro": lambda _checked=False: None,
        }
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(TOOLBAR),
                     "exec"), namespace)
        manager = namespace["_ToolbarManager"]()
        factory, verify = manager._make_button_action, manager.verify

        def create(host, icon):
            pair = factory(host, icon)
            created.append(pair)
            return pair

        def observe_verify():
            status = verify()
            verified.append((manager.host_toolbar.objectName(), status["ok"]))
            return status

        manager._make_button_action = create
        manager.verify = observe_verify
        return manager, main, main_toolbar, previous_fallback, events, created, verified

    def test_toolbar_second_main_layout_failure_uses_one_verified_fallback(self):
        manager, main, main_toolbar, previous, events, created, verified = (
            self._toolbar_install_layout_case(second_main_fails=True))
        status = manager.install()
        self.assertTrue(status["ok"])
        self.assertEqual(status["host"], "备用工具栏")
        self.assertEqual(verified, [("Main Toolbar", True),
                                   ("Main Toolbar", False),
                                   ("FBXTo3dsMax.FallbackToolbar", True)])
        self.assertEqual(events, [1, 2, 3])
        self.assertTrue(previous.deleted)
        self.assertEqual(main_toolbar.actions(), [])
        self.assertEqual(len(created), 2)
        self.assertTrue(all(item.deleted for item in created[0]))
        self.assertTrue(all(not item.deleted for item in created[1]))
        actions = [(toolbar, action) for toolbar in main.toolbars
                   for action in toolbar.actions()
                   if action.objectName() == "FBXTo3dsMax.OpenWidgetAction"]
        self.assertEqual(len(actions), 1)
        self.assertIs(actions[0][0], manager.fallback_toolbar)
        self.assertIs(actions[0][1], manager.widget_action)
        self.assertIs(manager.button, created[1][1])

    def test_toolbar_second_main_and_fallback_failures_cleanup_and_raise(self):
        manager, main, _main_toolbar, previous, events, created, verified = (
            self._toolbar_install_layout_case(second_main_fails=True,
                                              fallback_fails=True))
        with self.assertRaisesRegex(RuntimeError, "顶部按钮当前不可见"):
            manager.install()
        self.assertEqual(verified, [("Main Toolbar", True),
                                   ("Main Toolbar", False),
                                   ("FBXTo3dsMax.FallbackToolbar", False)])
        self.assertEqual(events, [1, 2, 3])
        self.assertTrue(previous.deleted)
        self.assertEqual(len(created), 2)
        self.assertTrue(all(item.deleted for pair in created for item in pair))
        self.assertFalse([action for toolbar in main.toolbars
                          for action in toolbar.actions()
                          if action.objectName() == "FBXTo3dsMax.OpenWidgetAction"])

    def test_toolbar_second_main_verify_pass_retains_main_without_fallback(self):
        manager, main, main_toolbar, previous, events, created, verified = (
            self._toolbar_install_layout_case())
        status = manager.install()
        self.assertTrue(status["ok"])
        self.assertEqual(status["host"], "主工具栏")
        self.assertEqual(verified, [("Main Toolbar", True), ("Main Toolbar", True)])
        self.assertEqual(events, [1, 2])
        self.assertTrue(previous.deleted)
        self.assertEqual(main.toolbars, [main_toolbar])
        self.assertIsNone(manager.fallback_toolbar)
        self.assertEqual(len(created), 1)
        self.assertIs(manager.widget_action, created[0][0])
        self.assertIs(manager.button, created[0][1])
        self.assertTrue(all(not item.deleted for item in created[0]))
        self.assertEqual(main_toolbar.actions(), [manager.widget_action])

    def test_toolbar_is_idempotent_and_dispatches_macro(self):
        main_window = _MainWindow()
        macro_calls = []
        main_toolbar = _ToolBar("主工具栏", main_window)
        main_toolbar.setObjectName("Main Toolbar")
        main_toolbar.show()
        main_window.addToolBar("top", main_toolbar)
        legacy_toolbar = _ToolBar("FBXTo3dsMax", main_window)
        legacy_toolbar.setObjectName("FBXTo3dsMax.Toolbar")
        legacy_toolbar.show()
        main_window.addToolBar("top", legacy_toolbar)

        runtime = types.SimpleNamespace(
            macros=types.SimpleNamespace(
                run=lambda category, name: macro_calls.append((category, name))
            ),
            messageBox=lambda *_args, **_kwargs: None,
        )
        pymxs = types.ModuleType("pymxs")
        pymxs.runtime = runtime

        qtcore = types.SimpleNamespace(
            Qt=types.SimpleNamespace(
                ToolBarArea=types.SimpleNamespace(TopToolBarArea="top"),
                ToolButtonStyle=types.SimpleNamespace(
                    ToolButtonTextBesideIcon="text-beside-icon"
                ),
            ),
            QSize=_Size,
            QPoint=_Point,
            QRect=_Rect,
            QTimer=_Timer,
        )
        qtgui = types.SimpleNamespace(
            QIcon=_Icon,
            QGuiApplication=_GuiApplication,
        )
        qtwidgets = types.SimpleNamespace(
            QToolBar=_ToolBar,
            QToolButton=_ToolButton,
            QWidgetAction=_WidgetAction,
            QApplication=_Application,
        )
        pyside6 = types.ModuleType("PySide6")
        pyside6.QtCore = qtcore
        pyside6.QtGui = qtgui
        pyside6.QtWidgets = qtwidgets
        qtmax = types.ModuleType("qtmax")
        qtmax.GetQMaxMainWindow = lambda: main_window

        replacements = {
            "pymxs": pymxs,
            "PySide6": pyside6,
            "qtmax": qtmax,
        }
        originals = {name: sys.modules.get(name) for name in replacements}
        api_slot = "_FBXTO3DSMAX_TOOLBAR_API"
        previous_api = getattr(builtins, api_slot, None)
        module_names = []
        try:
            sys.modules.update(replacements)
            for suffix in ("first", "second"):
                module_name = "_f2m_toolbar_mock_" + suffix
                module_names.append(module_name)
                spec = importlib.util.spec_from_file_location(module_name, TOOLBAR)
                self.assertIsNotNone(spec)
                self.assertIsNotNone(spec.loader)
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                api = getattr(builtins, api_slot)
                del module.__dict__["__file__"]
                status = api["install_and_schedule"]()
                self.assertTrue(status["ok"])
                self.assertEqual(len(module._manager._retry_timers), 3)
                self.assertEqual(len(main_window.toolbars), 1)
                self.assertIs(main_window.toolbars[0], main_toolbar)
                actions = [
                    action
                    for action in main_toolbar.actions()
                    if action.objectName()
                    == "FBXTo3dsMax.OpenWidgetAction"
                ]
                self.assertEqual(len(actions), 1)
                button = main_toolbar.widgetForAction(actions[0])
                self.assertEqual(button.text(), "FBX 转 MAX")
                self.assertGreaterEqual(button.width(), 100)
                self.assertFalse(button.icon().isNull())
                self.assertTrue(api["verify"]()["ok"])

                current_action = actions[0]
                _Application.active_modal = object()
                module._manager._safe_install()
                self.assertIs(
                    [
                        candidate
                        for candidate in main_toolbar.actions()
                        if candidate.objectName()
                        == "FBXTo3dsMax.OpenWidgetAction"
                    ][0],
                    current_action,
                )
                _Application.active_modal = None
                module._manager._safe_install()
                self.assertIs(
                    [
                        candidate
                        for candidate in main_toolbar.actions()
                        if candidate.objectName()
                        == "FBXTo3dsMax.OpenWidgetAction"
                    ][0],
                    current_action,
                )

            scheduled = list(module._manager._retry_timers)
            self.assertEqual(len(scheduled), 3)
            self.assertEqual(api["begin_shutdown"](), 1)
            self.assertTrue(module._manager.shutting_down)
            self.assertEqual(module._manager._retry_timers, [])
            self.assertTrue(all(not timer.active for timer in scheduled))
            self.assertTrue(all(timer.deleted for timer in scheduled))
            self.assertEqual(
                [
                    action
                    for action in main_toolbar.actions()
                    if action.objectName()
                    == "FBXTo3dsMax.OpenWidgetAction"
                ],
                [],
            )
            skipped = api["install_and_schedule"]()
            self.assertTrue(skipped["ok"])
            self.assertTrue(skipped["skipped"])
            self.assertEqual(module._manager._retry_timers, [])
            self.assertEqual(api["cancel_shutdown"](), 1)
            resumed = api["install_and_schedule"]()
            self.assertTrue(resumed["ok"])

            action = [
                action
                for action in main_toolbar.actions()
                if action.objectName() == "FBXTo3dsMax.OpenWidgetAction"
            ][0]
            button = main_toolbar.widgetForAction(action)
            button.clicked.emit()
            self.assertEqual(
                macro_calls, [("FBXTo3dsMax", "FBXTo3dsMax_Open")]
            )

            api = getattr(builtins, api_slot)
            self.assertEqual(api["uninstall"](), 1)
            self.assertEqual(main_window.toolbars, [main_toolbar])
            self.assertEqual(
                [
                    action
                    for action in main_toolbar.actions()
                    if action.objectName()
                    == "FBXTo3dsMax.OpenWidgetAction"
                ],
                [],
            )

            # A hidden/missing native Main Toolbar must produce one visible,
            # verified top fallback instead of another independent blank bar.
            main_toolbar.hide()
            module_name = "_f2m_toolbar_mock_fallback"
            module_names.append(module_name)
            spec = importlib.util.spec_from_file_location(module_name, TOOLBAR)
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            api = getattr(builtins, api_slot)
            del module.__dict__["__file__"]
            status = api["install_and_schedule"]()
            self.assertTrue(status["ok"])
            self.assertEqual(status["host"], "备用工具栏")
            fallbacks = [
                toolbar
                for toolbar in main_window.toolbars
                if toolbar.objectName()
                == "FBXTo3dsMax.FallbackToolbar"
            ]
            self.assertEqual(len(fallbacks), 1)
            fallback_actions = [
                action
                for action in fallbacks[0].actions()
                if action.objectName()
                == "FBXTo3dsMax.OpenWidgetAction"
            ]
            self.assertEqual(len(fallback_actions), 1)
            fallback_button = fallbacks[0].widgetForAction(
                fallback_actions[0]
            )
            self.assertEqual(fallback_button.text(), "FBX 转 MAX")
            self.assertTrue(fallback_button.isVisibleTo(main_window))
            self.assertEqual(api["uninstall"](), 1)
            self.assertEqual(main_window.toolbars, [main_toolbar])
        finally:
            _Application.active_modal = None
            _Timer.pending = []
            for module_name in module_names:
                sys.modules.pop(module_name, None)
            for name, original in originals.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original
            if previous_api is None:
                if hasattr(builtins, api_slot):
                    delattr(builtins, api_slot)
            else:
                setattr(builtins, api_slot, previous_api)


if __name__ == "__main__":
    unittest.main()
