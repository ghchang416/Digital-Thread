"""Explicit CAM mappings, derived from the repository's NX and Boss examples.

Percent stepover -> radial depth and stepdown -> scallop height are deliberately
omitted: these quantities are not interchangeable. No machining defaults here.
"""

WS = "MachiningWorkingstep"
OP = WS + ".its_operation.MachiningOperation"
TOOL = OP + ".its_tool.MachiningTool.MillingMachineCuttingTool"
TECH = OP + ".its_technology.Technology.MillingTechnology"
MILL = OP + ".MillingMachiningOperation.MillingTypeOperation"
FREE = MILL + ".FreeformOperation.its_machining_strategy.FreeformStrategy"
PLANAR = MILL + ".Two5DMillingOperation"

DEFAULT_MAPPINGS = {
    "powermill": {
        "macroRead.TOOLPATHNAME": WS + ".its_id",
        "macroRead.STRATEGY": OP + ".its_id",
        "ClsTool.ToolType": TOOL + ".its_id",
        "ClsTool.ToolD": TOOL + ".effective_cutting_diameter",
        "ClsTool.overhang": TOOL + ".overall_assembly_length",
        "ClsTool.ToolR": TOOL + ".MillingCuttingTool.edge_radius",
        "ClsTool.Length": TOOL + ".its_cutting_edges.CuttingComponent.tool_functional_length",
        "ClsTool.NumberOfFlutes": TOOL + ".MillingCuttingTool.number_of_effective_teeth",
        "macroRead.MCONDITION1_FEEDRATE": TECH + ".feedrate",
        "macroRead.MCONDITION1_SPINDLE": TECH + ".spindle",
        "macroRead.MCONDITION1_COOLANT": OP + ".its_machine_functions.MachineFunctions.MillingMachineFunctions.coolant",
        "macroRead.GENERAL_TOLERANCE": FREE + ".its_milling_tolerances.Tolerances.chordal_tolerance",
        "macroRead.CUTDIRECTION1_CUTDIR": FREE + ".cutmode",
        "macroRead.MCONDITION1_STEPOVER": FREE + ".stepover",
    },
    "nx": {
        "Object Information.Object name": WS + ".its_id",
        "Cutting Parameters.Cut Method": OP + ".its_id",
        "Feed Rate.Cut": TECH + ".feedrate",
        "Spindle Speed.Spindle Speed": TECH + ".spindle",
        "Tool Information.Tool Type": TOOL + ".its_id",
        "Tool Information.(D) Diameter": TOOL + ".effective_cutting_diameter",
        "Tool Information.(R1) Lower Radius": TOOL + ".MillingCuttingTool.edge_radius",
        "Tool Holder and In Process Workpiece.Shortest Collision-Free Tool": TOOL + ".overall_assembly_length",
        "Tool Information.Number of Flute": TOOL + ".MillingCuttingTool.number_of_effective_teeth",
        "Tool Information.(L) Length": TOOL + ".its_cutting_edges.CuttingComponent.tool_functional_length",
        "Tolerances.Intol": PLANAR + ".its_machining_strategy.Two5DMillingStrategy.its_milling_tolerances.Tolerances.chordal_tolerance",
        "Across Voids Parameters.Cut Direction Flag": PLANAR + ".its_machining_strategy.Two5DMillingStrategy.Unidirectional.cutmode",
        "Range.Depth per Cut": PLANAR + ".BottomAndSideMilling.axial_cutting_depth",
        "Geometry - Offset Value.Part Offset": PLANAR + ".BottomAndSideMilling.allowance_side",
    },
}
