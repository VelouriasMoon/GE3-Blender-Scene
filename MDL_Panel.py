from typing import Set
import bpy, json
from bpy.types import Context, Panel, PropertyGroup, Operator, UIList
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.props import StringProperty, BoolProperty, IntProperty

################################################################
############# Blender UI Lists for GE3 MDL Plugin ##############
################################################################

class GE3MDL_UL_Simplelist(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "ParameterName", text="", emboss=False, translate=False)

    def invoke(self, context, event):
        pass

class GE3MDL_UL_SAMPlist(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, "SamplerName", text="", emboss=False, translate=False)

    def invoke(self, context, event):
        pass

################################################################
############ Blender Operators for GE3 MDL Plugin ##############
################################################################

class GE3MDL_OP_ImportShaderJson(Operator, ImportHelper):
    bl_idname = "ge3.importshaderjson"
    bl_label = "Import Shader Info"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: StringProperty(default="*.ge3mat", options={'HIDDEN'}) # type: ignore

    def execute(self, context):
        if context.active_object.type != 'MESH':
            self.report({'ERROR'}, "Active Object is not mesh")
            return {'CANCELLED'}

        ge3mat = context.active_object.active_material.ge3mdl_material
        with open(self.filepath, 'r') as f:
            jdata = json.load(f)
            ge3mat.EFFE.ShaderName = jdata["EFFE"]["ShaderName"]

            ge3mat.TRSP.CullBackfaces = jdata["TRSP"]["CullBackfaces"]
            ge3mat.TRSP.Prop0x10 = jdata["TRSP"]["Prop0x10"]
            ge3mat.TRSP.UseAlpha = jdata["TRSP"]["UseAlpha"]
            ge3mat.TRSP.Prop0x18 = jdata["TRSP"]["Prop0x18"]
            ge3mat.TRSP.Prop0x1C = jdata["TRSP"]["Prop0x1C"]
            ge3mat.TRSP.Prop0x1C = jdata["TRSP"]["Prop0x1C"]
            ge3mat.TRSP.Prop0x24 = jdata["TRSP"]["Prop0x24"]

            ge3mat.VX_CSTS.Parameters.clear()
            ge3mat.has_VX_CSTS = False
            if len(jdata["VX_CSTS"]) > 0:
                ge3mat.has_VX_CSTS = True
                for param in jdata["VX_CSTS"]:
                    csts = ge3mat.VX_CSTS.Parameters.add()
                    csts.ParameterName = param


            ge3mat.VX_SAMP.Samplers.clear()
            ge3mat.has_VX_SAMP = False
            if len(jdata["VX_SAMP"]) > 0:
                ge3mat.has_VX_SAMP = True
                for param in jdata["VX_SAMP"]:
                    samp = ge3mat.VX_SAMP.Samplers.add()
                    samp.SamplerName = param["SamplerName"]
                    samp.TexturePath = param["TexturePath"]

            ge3mat.PX_CSTS.Parameters.clear()
            ge3mat.has_PX_CSTS = False
            if len(jdata["PX_CSTS"]) > 0:
                ge3mat.has_PX_CSTS = True
                for param in jdata["PX_CSTS"]:
                    csts = ge3mat.PX_CSTS.Parameters.add()
                    csts.ParameterName = param

            ge3mat.PX_SAMP.Samplers.clear()
            ge3mat.has_PX_SAMP = False
            if len(jdata["PX_SAMP"]) > 0:
                ge3mat.has_PX_SAMP = True
                for param in jdata["PX_SAMP"]:
                    samp = ge3mat.PX_SAMP.Samplers.add()
                    samp.SamplerName = param["SamplerName"]
                    samp.TexturePath = param["TexturePath"]

            ge3mat.VXSB.has_shbi_1 = jdata["VXSB"]["HasSHBI1"]
            ge3mat.VXSB.has_shbi_2 = jdata["VXSB"]["HasSHBI2"]
            ge3mat.VXSB.XXSH.Parameters.clear()
            ge3mat.VXSB.SHBI1.Parameters.clear()
            ge3mat.VXSB.SHBI2.Parameters.clear()
            for param in jdata["VXSB"]["VXSH"]:
                element = ge3mat.VXSB.XXSH.Parameters.add()
                element.ParameterName = param["ParameterName"]
                element.ParameterOffset = param["ParameterOffset"]
                element.ParameterType = param["ParameterType"]
                element.ParameterSize = param["ParameterSize"]
            for param in jdata["VXSB"]["SHBI1"]:
                element = ge3mat.VXSB.SHBI1.Parameters.add()
                element.ParameterName = param["ParameterName"]
                element.ParameterOffset = param["ParameterOffset"]
                element.ParameterSize = param["ParameterSize"]
            for param in jdata["VXSB"]["SHBI2"]:
                element = ge3mat.VXSB.SHBI2.Parameters.add()
                element.ParameterName = param["ParameterName"]
                element.ParameterOffset = param["ParameterOffset"]
                element.ParameterSize = param["ParameterSize"]

            ge3mat.PXSB.has_shbi_1 = jdata["PXSB"]["HasSHBI1"]
            ge3mat.PXSB.has_shbi_2 = jdata["PXSB"]["HasSHBI2"]
            ge3mat.PXSB.XXSH.Parameters.clear()
            ge3mat.PXSB.SHBI1.Parameters.clear()
            ge3mat.PXSB.SHBI2.Parameters.clear()
            for param in jdata["PXSB"]["PXSH"]:
                element = ge3mat.PXSB.XXSH.Parameters.add()
                element.ParameterName = param["ParameterName"]
                element.ParameterOffset = param["ParameterOffset"]
                element.ParameterType = param["ParameterType"]
                element.ParameterSize = param["ParameterSize"]
            for param in jdata["PXSB"]["SHBI1"]:
                element = ge3mat.PXSB.SHBI1.Parameters.add()
                element.ParameterName = param["ParameterName"]
                element.ParameterOffset = param["ParameterOffset"]
                element.ParameterSize = param["ParameterSize"]
            for param in jdata["PXSB"]["SHBI2"]:
                element = ge3mat.PXSB.SHBI2.Parameters.add()
                element.ParameterName = param["ParameterName"]
                element.ParameterOffset = param["ParameterOffset"]
                element.ParameterSize = param["ParameterSize"]

            ge3mat.Constants.SHCOs.clear()
            for param in jdata["Constants"]["SHCOs"]:
                SHCO = ge3mat.Constants.SHCOs.add()
                SHCO.Name = param["Name"]
                SHCO.SHCORawData = param["SHCORawData"]

            ge3mat.Constants.SMSTs.clear()
            for param in jdata["Constants"]["SMSTs"]:
                SMST = ge3mat.Constants.SMSTs.add()
                SMST.Name = param["Name"]
                SMST.SMSTRawData = param["SMSTRawData"]


        ge3mat.dataImported = True
        self.report({'INFO'}, "GE3 Shader Info Imported")
        return {'FINISHED'}

class GE3MDL_OP_ExportShaderJson(Operator, ExportHelper):
    bl_idname = "ge3.exportshaderjson"
    bl_label = "Export Shader Info"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: StringProperty(default="*.ge3mat", options={'HIDDEN'}) # type: ignore
    filename_ext = ".ge3mat"

    def execute(self, context):
        if context.active_object.type != 'MESH':
            self.report({'ERROR'}, "Active Object is not mesh")
            return {'CANCELLED'}
        if context.active_object.active_material.ge3mdl_material.dataImported == False:
            self.report({'ERROR'}, "Active Material has no Shader Info")
            return {'CANCELLED'}

        ge3mat = context.active_object.active_material.ge3mdl_material
        jdata = {}
        jdata["EFFE"] = {}
        jdata["EFFE"]["ShaderName"] = ge3mat.EFFE.ShaderName

        jdata["TRSP"] = {}
        jdata["TRSP"]["CullBackfaces"] = ge3mat.TRSP.CullBackfaces
        jdata["TRSP"]["Prop0x10"] = ge3mat.TRSP.Prop0x10
        jdata["TRSP"]["UseAlpha"] = ge3mat.TRSP.UseAlpha
        jdata["TRSP"]["Prop0x18"] = ge3mat.TRSP.Prop0x18
        jdata["TRSP"]["Prop0x1C"] = ge3mat.TRSP.Prop0x1C
        jdata["TRSP"]["Prop0x20"] = ge3mat.TRSP.Prop0x20
        jdata["TRSP"]["Prop0x24"] = ge3mat.TRSP.Prop0x24

        jdata["VX_CSTS"] = []
        for param in ge3mat.VX_CSTS.Parameters:
            jdata["VX_CSTS"].append(param.ParameterName)

        jdata["VX_SAMP"] = []
        for param in ge3mat.VX_SAMP.Samplers:
            SAMP = {}
            SAMP["SamplerName"] = param.SamplerName
            SAMP["TexturePath"] = param.TexturePath
            jdata["VX_SAMP"].append(SAMP)

        jdata["PX_CSTS"] = []
        for param in ge3mat.PX_CSTS.Parameters:
            jdata["PX_CSTS"].append(param.ParameterName)

        jdata["PX_SAMP"] = []
        for param in ge3mat.PX_SAMP.Samplers:
            SAMP = {}
            SAMP["SamplerName"] = param.SamplerName
            SAMP["TexturePath"] = param.TexturePath
            jdata["PX_SAMP"].append(SAMP)

        jdata["VXSB"] = {}
        jdata["VXSB"]["HasSHBI1"] = ge3mat.VXSB.has_shbi_1
        jdata["VXSB"]["HasSHBI2"] = ge3mat.VXSB.has_shbi_2
        jdata["VXSB"]["VXSH"] = []
        for param in ge3mat.VXSB.XXSH.Parameters:
            Element = {}
            Element["ParameterName"] = param.ParameterName
            Element["ParameterOffset"] = param.ParameterOffset
            Element["ParameterType"] = param.ParameterType
            Element["ParameterSize"] = param.ParameterSize
            jdata["VXSB"]["VXSH"].append(Element)
        jdata["VXSB"]["SHBI1"] = []
        for param in ge3mat.VXSB.SHBI1.Parameters:
            Element = {}
            Element["ParameterName"] = param.ParameterName
            Element["ParameterOffset"] = param.ParameterOffset
            Element["ParameterSize"] = param.ParameterSize
            jdata["VXSB"]["SHBI1"].append(Element)
        jdata["VXSB"]["SHBI2"] = []
        for param in ge3mat.VXSB.SHBI2.Parameters:
            Element = {}
            Element["ParameterName"] = param.ParameterName
            Element["ParameterOffset"] = param.ParameterOffset
            Element["ParameterSize"] = param.ParameterSize
            jdata["VXSB"]["SHBI2"].append(Element)

        jdata["PXSB"] = {}
        jdata["PXSB"]["HasSHBI1"] = ge3mat.PXSB.has_shbi_1
        jdata["PXSB"]["HasSHBI2"] = ge3mat.PXSB.has_shbi_2
        jdata["PXSB"]["PXSH"] = []
        for param in ge3mat.PXSB.XXSH.Parameters:
            Element = {}
            Element["ParameterName"] = param.ParameterName
            Element["ParameterOffset"] = param.ParameterOffset
            Element["ParameterType"] = param.ParameterType
            Element["ParameterSize"] = param.ParameterSize
            jdata["PXSB"]["PXSH"].append(Element)
        jdata["PXSB"]["SHBI1"] = []
        for param in ge3mat.PXSB.SHBI1.Parameters:
            Element = {}
            Element["ParameterName"] = param.ParameterName
            Element["ParameterOffset"] = param.ParameterOffset
            Element["ParameterSize"] = param.ParameterSize
            jdata["PXSB"]["SHBI1"].append(Element)
        jdata["PXSB"]["SHBI2"] = []
        for param in ge3mat.PXSB.SHBI2.Parameters:
            Element = {}
            Element["ParameterName"] = param.ParameterName
            Element["ParameterOffset"] = param.ParameterOffset
            Element["ParameterSize"] = param.ParameterSize
            jdata["PXSB"]["SHBI2"].append(Element)

        jdata["Constants"] = {}
        jdata["Constants"]["SHCOs"] = []
        for param in ge3mat.Constants.SHCOs:
            SHCO = {}
            SHCO["Name"] = param.Name
            SHCO["SHCORawData"] = param.SHCORawData
            jdata["Constants"]["SHCOs"].append(SHCO)
        jdata["Constants"]["SMSTs"] = []
        for param in ge3mat.Constants.SMSTs:
            SMST = {}
            SMST["Name"] = param.Name
            SMST["SMSTRawData"] = param.SMSTRawData
            jdata["Constants"]["SMSTs"].append(SMST)

        with open(self.filepath, "w") as file:
            json.dump(jdata, file, indent=4)

        self.report({'INFO'}, "GE3 Shader Info Exported")
        return {'FINISHED'}


################################################################
############ Blender UI Panels for GE3 MDL Plugin ##############
################################################################

class GE3MDL_PT_ShaderMenu(Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "God Eater 3"
    bl_label = "God Eater 3 Shaders"
    bl_idname = "ge3_PT_shader_menu"

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.label(text="God Eater 3 Shader Tools:")
        if context.active_object is None:
            return
        col.label(text=f"Active Object: {context.active_object.name}")
        col.separator(type='LINE')
        if context.active_object.type == 'MESH':
            mat = context.active_object.active_material
            col = layout.column()
            col.label(text=f"Active Material: {mat.name}")
            col = layout.column(align=True)
            col.operator("ge3.importshaderjson", text="Import Shader Info", icon='IMPORT')
            col.operator("ge3.exportshaderjson", text="Export Shader Info", icon='EXPORT')
            col = layout.column()
            if mat.ge3mdl_material.dataImported:
                col.label(text="Shader Name:")
                col.prop(mat.ge3mdl_material.EFFE, "ShaderName", text="", icon='SHADERFX')
                col.separator(type='LINE')

                head, pan = layout.panel_prop(mat.ge3mdl_material, "showTRSP")
                head.label(text="TRSP Properties")
                if pan:
                    if mat.ge3mdl_material.showTRSP:
                        pan.use_property_split = True
                        pan.use_property_decorate = False
                    draw_trps_panel(pan, mat)

                col = layout.column()
                col.separator(type='LINE')

                verthead, vertpan = layout.panel_prop(mat.ge3mdl_material, "showVertex")
                verthead.label(text="Vertex Shader Properties")
                if vertpan:
                        if mat.ge3mdl_material.has_VX_CSTS:
                            head, pan = vertpan.panel_prop(mat.ge3mdl_material, "showVXCSTS")
                            head.label(text="CSTS Properties")
                            if pan:
                                draw_vx_csts_panel(pan, mat)
                        if mat.ge3mdl_material.has_VX_SAMP:
                            head, pan = vertpan.panel_prop(mat.ge3mdl_material, "showVXSAMP")
                            head.label(text="SAMP Properties")
                            if pan:
                                draw_vx_samp_panel(pan, mat)
                        head, pan = vertpan.panel_prop(mat.ge3mdl_material, "showVXSB")
                        head.label(text="VXSB Properties")
                        if pan:
                            draw_vxsb_panel(pan, mat.ge3mdl_material.VXSB)

                col = layout.column()
                col.separator(type='LINE')

                pixhead, pixpan = layout.panel_prop(mat.ge3mdl_material, "showPixel")
                pixhead.label(text="Pixel Shader Properties")
                if pixpan:
                        if mat.ge3mdl_material.has_PX_CSTS:
                            head, pan = pixpan.panel_prop(mat.ge3mdl_material, "showPXCSTS")
                            head.label(text="CSTS Properties")
                            if pan:
                                draw_px_csts_panel(pan, mat)
                        if mat.ge3mdl_material.has_PX_SAMP:
                            head, pan = pixpan.panel_prop(mat.ge3mdl_material, "showPXSAMP")
                            head.label(text="SAMP Properties")
                            if pan:
                                draw_px_samp_panel(pan, mat)
                        head, pan = pixpan.panel_prop(mat.ge3mdl_material, "showPXSB")
                        head.label(text="PXSB Properties")
                        if pan:
                            draw_pxsb_panel(pan, mat.ge3mdl_material.PXSB)

            else:
                col.label(text="Material has no Shader Info", icon='ERROR')
        else:
            col.label(text="No Mesh Selected", icon='ERROR')

def draw_vxsb_panel(layout: bpy.types.UILayout, xxsb):
    col = layout.column()
    col.label(text="VXSH Properies:")
    col.template_list("GE3MDL_UL_Simplelist", "templatelist_UL_VXSB_XXSH", xxsb.XXSH, "Parameters", xxsb.XXSH, "Active_Index", rows=4)

    if xxsb.has_shbi_1:
        col.label(text="SHBI 1 Properies:")
        col.template_list("GE3MDL_UL_Simplelist", "templatelist_UL_VXSB_SHBI1", xxsb.SHBI1, "Parameters", xxsb.SHBI1, "Active_Index", rows=4)

    if xxsb.has_shbi_2:
        col.label(text="SHBI 2 Properies:")
        col.template_list("GE3MDL_UL_Simplelist", "templatelist_UL_VXSB_SHBI2", xxsb.SHBI2, "Parameters", xxsb.SHBI2, "Active_Index", rows=4)

def draw_pxsb_panel(layout: bpy.types.UILayout, xxsb):
    col = layout.column()
    col.label(text="PXSH Properies:")
    col.template_list("GE3MDL_UL_Simplelist", "templatelist_UL_PXSB_XXSH", xxsb.XXSH, "Parameters", xxsb.XXSH, "Active_Index", rows=4)

    if xxsb.has_shbi_1:
        col.label(text="SHBI 1 Properies:")
        col.template_list("GE3MDL_UL_Simplelist", "templatelist_UL_PXSB_SHBI1", xxsb.SHBI1, "Parameters", xxsb.SHBI1, "Active_Index", rows=4)

    if xxsb.has_shbi_2:
        col.label(text="SHBI 2 Properies:")
        col.template_list("GE3MDL_UL_Simplelist", "templatelist_UL_PXSB_SHBI2", xxsb.SHBI2, "Parameters", xxsb.SHBI2, "Active_Index", rows=4)
        

def draw_trps_panel(layout: bpy.types.UILayout, mat):
    col = layout.column()
    col.prop(mat.ge3mdl_material.TRSP, "CullBackfaces", text="Cull Backfaces")
    col.prop(mat.ge3mdl_material.TRSP, "UseAlpha", text="Use Alpha")
    col.prop(mat.ge3mdl_material.TRSP, "Prop0x10", text="Prop 0x10")
    col.prop(mat.ge3mdl_material.TRSP, "Prop0x18", text="Prop 0x18")
    col.prop(mat.ge3mdl_material.TRSP, "Prop0x1C", text="Prop 0x1C")
    col.prop(mat.ge3mdl_material.TRSP, "Prop0x20", text="Prop 0x20")
    col.prop(mat.ge3mdl_material.TRSP, "Prop0x24", text="Prop 0x24")

def get_shco(mat, name):
    for SHCO in mat.ge3mdl_material.Constants.SHCOs:
        if SHCO.Name == name:
            return SHCO
    return None
        
def draw_vx_csts_panel(layout: bpy.types.UILayout, mat):
    col = layout.column()
    col.label(text="CVTS Values:")
    col.template_list("GE3MDL_UL_Simplelist", "templatelist_UL_VX_CSTV", mat.ge3mdl_material.VX_CSTS, "Parameters", mat.ge3mdl_material.VX_CSTS, "Active_Index", rows=4)
    col.label(text="SCHO Raw Values:")
    if len(mat.ge3mdl_material.VX_CSTS.Parameters) > 0:
        shcoName = mat.ge3mdl_material.VX_CSTS.Parameters[mat.ge3mdl_material.VX_CSTS.Active_Index].ParameterName
        SHCO = get_shco(mat, shcoName)
        if SHCO is not None:
            col.prop(SHCO, "SHCORawData", text="")

def draw_px_csts_panel(layout: bpy.types.UILayout, mat):
    col = layout.column()
    col.label(text="CVTS Values:")
    col.template_list("GE3MDL_UL_Simplelist", "templatelist_UL_PX_CSTV", mat.ge3mdl_material.PX_CSTS, "Parameters", mat.ge3mdl_material.PX_CSTS, "Active_Index", rows=4)
    col.label(text="SCHO Raw Values:")
    if len(mat.ge3mdl_material.PX_CSTS.Parameters) > 0:
        shcoName = mat.ge3mdl_material.PX_CSTS.Parameters[mat.ge3mdl_material.PX_CSTS.Active_Index].ParameterName
        SHCO = get_shco(mat, shcoName)
        if SHCO is not None:
            col.prop(SHCO, "SHCORawData", text="")

def get_smst(mat, name):
    for SMST in mat.ge3mdl_material.Constants.SMSTs:
            if SMST.Name == name:
                return SMST
    return None

def draw_vx_samp_panel(layout: bpy.types.UILayout, mat):
    col = layout.column()
    col.label(text="Texture Samplers:")
    col.template_list("GE3MDL_UL_SAMPlist", "templatelist_UL_VX_SAMP", mat.ge3mdl_material.VX_SAMP, "Samplers", mat.ge3mdl_material.VX_SAMP, "Active_Index", rows=4)

    if len(mat.ge3mdl_material.VX_SAMP.Samplers) > 0:
        index = mat.ge3mdl_material.VX_SAMP.Active_Index
        SAMPs = mat.ge3mdl_material.VX_SAMP.Samplers
        col.label(text="Texture Path:")
        col.prop(SAMPs[index], "TexturePath", text="", icon='TEXTURE')
        smstName = mat.ge3mdl_material.VX_SAMP.Samplers[mat.ge3mdl_material.VX_SAMP.Active_Index].SamplerName
        col.label(text="SMST Raw Values:")
        SMST = get_smst(mat, smstName)
        if SMST is not None:
            col.prop(SMST, "SMSTRawData", text="")

def draw_px_samp_panel(layout: bpy.types.UILayout, mat):
    col = layout.column()
    col.label(text="Texture Samplers:")
    col.template_list("GE3MDL_UL_SAMPlist", "templatelist_UL_PX_SAMP", mat.ge3mdl_material.PX_SAMP, "Samplers", mat.ge3mdl_material.PX_SAMP, "Active_Index", rows=4)

    if len(mat.ge3mdl_material.PX_SAMP.Samplers) > 0:
        index = mat.ge3mdl_material.PX_SAMP.Active_Index
        SAMPs = mat.ge3mdl_material.PX_SAMP.Samplers
        col.label(text="Texture Path:")
        col.prop(SAMPs[index], "TexturePath", text="", icon='TEXTURE')
        smstName = mat.ge3mdl_material.PX_SAMP.Samplers[mat.ge3mdl_material.PX_SAMP.Active_Index].SamplerName
        col.label(text="SMST Raw Values:")
        SMST = get_smst(mat, smstName)
        if SMST is not None:
            col.prop(SMST, "SMSTRawData", text="")