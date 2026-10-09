/* Original canopy exercise. Use only in a new empty scene. */
(
    local sourceDir = getFilenamePath (getSourceFileName())
    local pathClass = dotNetClass "System.IO.Path"
    local demoPath = pathClass.GetFullPath (sourceDir + "create_demo_scene.py")
    if not doesFileExist demoPath do throw "Missing create_demo_scene.py beside Create_Demo.ms."
    local pythonPath = substituteString demoPath "\\" "/"
    pythonPath = substituteString pythonPath "'" "\\'"
    local script = "import runpy as _f2m_demo_runpy\n"
    script += "from pathlib import Path as _f2m_demo_Path\n"
    script += "_f2m_demo_path = _f2m_demo_Path('" + pythonPath + "').resolve()\n"
    script += "try:\n"
    script += "    _f2m_demo_scope = _f2m_demo_runpy.run_path(str(_f2m_demo_path))\n"
    script += "    if _f2m_demo_Path(_f2m_demo_scope.get('__file__', '')).resolve() != _f2m_demo_path:\n"
    script += "        raise RuntimeError('Original demo source identity differs')\n"
    script += "    if _f2m_demo_scope.get('DEMO_SCHEMA') != 'f2m-original-canopy-1':\n"
    script += "        raise RuntimeError('Original demo schema differs')\n"
    script += "    if not callable(_f2m_demo_scope.get('create_demo_scene')):\n"
    script += "        raise RuntimeError('Original demo entry is missing')\n"
    script += "    _f2m_demo_scope['create_demo_scene']()\n"
    script += "finally:\n"
    script += "    globals().pop('_f2m_demo_scope', None)\n"
    script += "    globals().pop('_f2m_demo_path', None)\n"
    script += "    globals().pop('_f2m_demo_runpy', None)\n"
    script += "    globals().pop('_f2m_demo_Path', None)\n"
    local result = python.Execute script throwOnError:true clearUndoBuffer:false
    if result != #success do throw ("Original demo preparation failed: " + result as string)
)
