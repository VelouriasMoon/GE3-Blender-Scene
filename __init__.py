# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

bl_info = {
    "name": "God Eater 3 MDL",
    "author": "Moonling",
    "description": "",
    "blender": (5, 00, 0),
    "version": (1, 0, 0),
    "location": "",
    "warning": "",
    "category": "Generic",
}

import bpy
from . MDL_Props import *
from . MDL_Importer import *
from . MDL_Export import *
from . MDL_Panel import *

filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), "GE3Nodes.blend")
def AppendNodeTree():
    print(f"Appending NodeTree from: {filepath}")
    if os.path.isfile(filepath) and "GE3MeshSplit" not in bpy.data.node_groups:
        bpy.ops.wm.append(
            filepath=str(filepath + "\\NodeTree\\GE3MeshSplit"),
            directory=str(filepath + "\\NodeTree"),
            filename="GE3MeshSplit",
            set_fake=True
        )

classes = (
    GE3MDL_Mat_TRPS,
    GE3MDL_Mat_CSTV,
    GE3MDL_Mat_CSTS,
    GE3MDL_Mat_EFFE,
    GE3MDL_Mat_SSTV,
    GE3MDL_Mat_SAMP,
    GE3MDL_Shader_XXSHElement,
    GE3MDL_Shader_XXSH,
    GE3MDL_Shader_SHBIElement,
    GE3MDL_Shader_SHBI,
    GE3MDL_Shader_XXSB,
    GE3MDL_Shader_SHCO,
    GE3MDL_Shader_SMST,
    GE3MDL_Shader_Constants,
    GE3MDL_Material,

    GE3MDL_UL_Simplelist,
    GE3MDL_UL_SAMPlist,
    GE3MDL_OP_ImportShaderJson,
    GE3MDL_OP_ExportShaderJson,
    GE3MDL_PT_ShaderMenu,

    ImportMDL,
    ImportSKL,
    ExportMDL,
    ExportSKL,
)

def draw_mdl_export(self, context):
    self.layout.operator(ExportMDL.bl_idname, text="GE3 Model (.mdl)")
def draw_skl_export(self, context):
    self.layout.operator(ExportSKL.bl_idname, text="GE3 Skeleton (.skl)")

def draw_mdl_import(self, context):
    self.layout.operator(ImportMDL.bl_idname, text="GE3 Model (.mdl)")
def draw_skl_import(self, context):
    self.layout.operator(ImportSKL.bl_idname, text="GE3 Skeleton (.skl)")

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Material.ge3mdl_material = bpy.props.PointerProperty(type=GE3MDL_Material)
    bpy.types.TOPBAR_MT_file_import.append(draw_mdl_import)
    bpy.types.TOPBAR_MT_file_import.append(draw_skl_import)
    bpy.types.TOPBAR_MT_file_export.append(draw_mdl_export)
    bpy.types.TOPBAR_MT_file_export.append(draw_skl_export)
    bpy.app.timers.register(AppendNodeTree, first_interval=0.1)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Material.ge3mdl_material
    bpy.types.TOPBAR_MT_file_import.remove(draw_mdl_import)
    bpy.types.TOPBAR_MT_file_import.remove(draw_skl_import)
    bpy.types.TOPBAR_MT_file_export.remove(draw_mdl_export)
    bpy.types.TOPBAR_MT_file_export.remove(draw_skl_export)
