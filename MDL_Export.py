import struct, os, json, enum, io
import mathutils, math
from typing import Set
import bpy, bmesh
from bpy_extras.io_utils import ExportHelper
from bpy.types import Context, Operator
from bpy.props import StringProperty, BoolProperty, FloatProperty, EnumProperty

ShaderInfoLoad = False
ShaderInfoJson = "ShaderInfo.json"
ShaderInfo = {}

def loadShaderInfo():
    filepath = os.path.join(os.path.dirname(os.path.realpath(__file__)), ShaderInfoJson)
    if not os.path.isfile(filepath):
        print(f"ShaderInfo.json file not found: {filepath}")
        return False
    with open(filepath, 'r') as f:
        jsonfile = json.load(f)
        for shader in jsonfile:
            ShaderInfo[shader] = jsonfile[shader]
    global ShaderInfoLoad
    ShaderInfoLoad = True
    return True

def crc32_bzip2(data: bytes) -> int:
    crc = 0xffffffff
    for byte in data:
        # BZIP2 shifts the byte into the high 24 bits
        crc ^= byte << 24
        for _ in range(8):
            if crc & 0x80000000:
                # Uses the standard 0x04C11DB7 polynomial
                crc = (crc << 1) ^ 0x04c11db7
            else:
                crc = crc << 1
            crc &= 0xffffffff  # Keep it strictly to a 32-bit integer
            
    # BZIP2 XORs the final result with 0xffffffff (represented here by bitwise NOT)
    return ~crc & 0xffffffff

def custom_normalize(weights):
    if sum(weights)  == 0:
        return weights
    normalized_weights = [int(weight * 255) for weight in weights]
    
    diff = 255 - sum(normalized_weights)
    if diff != 0:
        normalized_weights = [w + diff // len(normalized_weights) for w in normalized_weights]
        normalized_weights[-1] += diff % len(normalized_weights)
    
    return normalized_weights

def unpack_16bit_normal(nx_16bit, ny_16bit):
    x = nx_16bit / 32767.0
    y = ny_16bit / 32767.0
    
    x = max(-1.0, min(1.0, x))
    y = max(-1.0, min(1.0, y))
    
    z_squared = 1.0 - (x**2 + y**2)
    z = math.sqrt(max(0.0, z_squared)) 
    
    return x, y, z

def clamp(num, minimum, maximum):
    return max(min(num, maximum), minimum)

def encode_string_16bytes(text: str) -> bytes:
    text_bytes = text.encode('utf-8')
    if len(text_bytes) <= 15:
        # Pad with null bytes to 16 bytes
        return text_bytes + b'\x00' * (16 - len(text_bytes))
    else:
        # Take first 7 bytes, add '~', add last 8 bytes (including null terminator)
        first_7 = text_bytes[:7]
        last_7 = text_bytes[-7:]
        result = first_7 + b'~' + last_7 + b'\x00'
        return result[:16]  # Ensure exactly 16 bytes

################################################################
#########                  Exporters                 ###########
################################################################

class ExportMDL(Operator, ExportHelper):
    bl_idname = "export_scene.mdl"
    bl_label = "Export GE3 Model"
    bl_options = {'PRESET'}

    filename_ext = ".mdl"
    filter_glob: StringProperty(default="*.mdl", options={'HIDDEN'}, maxlen=255,) # type: ignore
    selectedonly: BoolProperty(name="Selected Only", default=True) # type: ignore
    exportplatform : EnumProperty( name="Platform",
        items=[
            ("DX11", "Windows", "For the PC version of the game"),
            #("NX", "Nintendo Switch", "For the Switch version of the game")
        ],
        default="DX11"
    )# type: ignore
    applysplit: BoolProperty(name="Use Face Split Fix", description="Applys a modifier to the final outfit to split faces by UV island and sharp.", default=True) # type: ignore
    materialsplit: BoolProperty(name="Separate Objects by Material", description="Only one material per object is supported. Enabling this will Split objects with multiple materials first", default=True) # type: ignore

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        col = box.column()
        col.label(text="General", icon='SETTINGS')
        col.prop(self, "selectedonly")
        col.prop(self, "exportplatform")
        box = layout.box()
        col = box.column()
        col.label(text="Mesh", icon='MESH_DATA')
        col.prop(self, "applysplit")
        col.prop(self, "materialsplit")

    def execute(self, context):
        if self.selectedonly and len(context.selected_objects) <= 0:
            self.report({'ERROR'}, "No Objects selected")
            return {'CANCELLED'}

        AllObjects = context.selected_objects if self.selectedonly else context.scene.objects

        if self.materialsplit:
            for obj in AllObjects:
                if obj.type == 'MESH':
                    self.report({'INFO'}, f"Splitting Object Materials '{obj.name}'")
                    if bpy.context.object.mode != 'OBJECT':
                        bpy.ops.object.mode_set(mode='OBJECT')
                    bpy.context.view_layer.objects.active = obj
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.select_all(action='SELECT')
                    bpy.ops.mesh.separate(type='MATERIAL')
                    bpy.ops.object.mode_set(mode='OBJECT')
            AllObjects = context.selectable_objects if self.selectedonly else context.scene.objects


        Armature = None
        SceneRoot = None
        ExportableObjects = []
        HasMorph = False
        for obj in AllObjects:
            if obj.type == 'ARMATURE':
                if Armature is None:
                    Armature = obj
                else:
                    self.report({'WARNING'}, f"Multiple Armatures found during export, using {Armature.name}.")
            elif obj.type == 'MESH':
                ExportableObjects.append(obj)
                if HasMorph == False: 
                    if obj.data.shape_keys is not None and len(obj.data.shape_keys.key_blocks) > 1:
                        HasMorph = True
            elif obj.type == 'EMPTY' and SceneRoot is None:
                SceneRoot = obj

        if SceneRoot is None:
            self.report({'WARNING'}, "Unable to find SceneRoot, Trying to determine scene name from objects")
        
        f = io.BytesIO()

        f.write(b'KPKy')
        f.write(struct.pack('<II', 6, 0)) #Size to write later
        f.write(struct.pack('<IIIIII', 0, 0, 0, 0, 0, 0 )) #dummy offsets
        f.write(struct.pack('<IIIIII', 0, 0, 0, 0, 0, 0 )) #dummy sizes
        f.write(struct.pack('<I', 0))

        #Write MESH
        MESHOffset = f.tell()
        MESHSize = writeMESH(self, context, f, ExportableObjects, SceneRoot, Armature)
        while (f.tell() % 16 != 0):
            f.write(b'\x00')

        #Write GPR
        GPROffset = f.tell()
        GPRSize = writeGPR(self, context, f, ExportableObjects, SceneRoot)
        while (f.tell() % 16 != 0):
            f.write(b'\x00')

        #Write NODT
        NODTOffset = f.tell()
        NODTSize = writeNODT(self, context, f)

        if Armature is not None:
            #Write BRNT
            BNTROffset = f.tell()
            BNTRSize = writeBRNT(self, context, f, Armature)
            while (f.tell() % 16 != 0):
                f.write(b'\x00')
            
            _60SEOffset = f.tell()
            _60SESize = write60SE(self, context, f, Armature)
            while (f.tell() % 16 != 0):
                f.write(b'\x00')
        else:
            BNTROffset, BNTRSize, _60SEOffset, _60SESize = 0, 0, 0, 0

        if HasMorph:
            MORPOffset = f.tell()
            MORPSize = writeMESH(self, context, f, ExportableObjects, SceneRoot, Armature, True)
        else:
            MORPOffset, MORPSize = 0, 0

        f.seek(12)
        f.write(struct.pack('<IIIIII', MESHOffset, GPROffset, 0, BNTROffset, _60SEOffset, MORPOffset )) #dummy offsets
        f.write(struct.pack('<IIIIII', MESHSize, GPRSize, 0, BNTRSize, _60SESize, MORPSize )) #dummy sizes

        with open(self.filepath, 'w+b') as file:
            file.write(f.getbuffer())

        self.report({'INFO'}, "Export Done.")
        f.close()
        return {'FINISHED'}

class ExportSKL(Operator, ExportHelper):
    bl_idname = "export_scene.skl"
    bl_label = "Export GE3 Skeleton"
    bl_options = {'PRESET'}

    filename_ext = ".skl"
    filter_glob: StringProperty(default="*.skl", options={'HIDDEN'}, maxlen=255,) # type: ignore
    selectedonly: BoolProperty(name="Selected Only", default=True) # type: ignore

    def execute(self, context):
        if self.selectedonly and len(context.selected_objects) <= 0:
            self.report({'ERROR'}, "No Objects selected")

        exportableObjects = context.selected_objects if self.selectedonly else context.scene.objects
        Armature = None
        for obj in exportableObjects:
            if obj.type == 'ARMATURE':
                Armature = obj
        with open(self.filepath, 'w+b') as f:
            write60SE(self, context, f, Armature)

        self.report({'INFO'}, "Export Done.")
        return {'FINISHED'}

################################################################
#########              Write Functions               ###########
################################################################

def StringTableAddString(StringTable, str):
    fast_table = set(StringTable)
    if str not in fast_table:
        StringTable.append(str)

def writeMESH(self, context, f: io.BytesIO, exportable_objects, Scene: bpy.types.Object, Armature: bpy.types.Object, bisMorph = False):
    if bisMorph:
        f.write(b'MORP')
    else:
        f.write(b'MESH')
    f.write(struct.pack('<I', 0 )) #Size to write later
    sectionStart = f.tell()

    #Rem, static section with creator string
    PluginCreatorString = b"Blender GE3 MDL Plugin Version 1.0.0 by Moonling"
    f.write(b'REM\x00')
    f.write(struct.pack('<I', len(PluginCreatorString)))
    f.write(PluginCreatorString)

    #While we're grabbing all the strings for the string table let's put these into lists so i can write them by type and not by obj
    TRSPs = []
    EFFEs = []
    CSTSs = []
    SAMPs = []
    Mats = []

    if Scene is None:
        SceneName = "VisualSceneNode"
        ModelName = exportable_objects[0].users_collection[0].name
    else:
        SceneName = Scene.name
        ModelName = Scene.users_collection[0].name

    #start the string table calculation hell
    StringTable = []
    StringTableAddString(StringTable, ModelName)
    StringTableAddString(StringTable, SceneName)
    StringTableAddString(StringTable, "Default")    #Used for VARI section

    #Loop through the exportable objects and grab/make strings will need for the table
    for obj in exportable_objects:
        StringTableAddString(StringTable, obj.name)
        mat = obj.active_material
        if not hasattr(mat, "ge3mdl_material"):
            self.report({'WARNING'}, f"Object {obj.name} missing ge3 material prop")
            continue
        if not mat.ge3mdl_material.dataImported:
            self.report({'WARNING'}, f"Object {obj.name} missing ge3 material info")
            continue

        if bisMorph and obj.data.shape_keys is not None and len(obj.data.shape_keys.key_blocks) > 1:
            for morph in obj.data.shape_keys.key_blocks:
                StringTableAddString(StringTable, morph.name)
                StringTableAddString(StringTable, "mesh_Brow_mesh-morph")
                StringTableAddString(StringTable, "mesh_Mouth_mesh-morph")
                StringTableAddString(StringTable, "mesh_Eye_mesh-morph")


        #Optimize models that use the same mat on multiple meshes, like faces
        if mat not in Mats:
            Mats.append(mat)
            TRSPs.append((mat.ge3mdl_material.TRSP, mat))
            EFFEs.append((mat.ge3mdl_material.EFFE, mat))
            if mat.ge3mdl_material.has_VX_CSTS:
                CSTSs.append((mat.ge3mdl_material.VX_CSTS, mat))
            if mat.ge3mdl_material.has_PX_CSTS:
                CSTSs.append((mat.ge3mdl_material.PX_CSTS, mat))
            if mat.ge3mdl_material.has_VX_SAMP:
                SAMPs.append((mat.ge3mdl_material.VX_SAMP, mat))
            if mat.ge3mdl_material.has_PX_SAMP:
                SAMPs.append((mat.ge3mdl_material.PX_SAMP, mat))
        
        StringTableAddString(StringTable, mat.name)
        StringTableAddString(StringTable, mat.name.replace("_mat", "_sg"))
        ge3mat = mat.ge3mdl_material
        StringTableAddString(StringTable, f"{mat.name}-fx")
        StringTableAddString(StringTable, ge3mat.EFFE.ShaderName)

        for param in mat.ge3mdl_material.VX_CSTS.Parameters:
            StringTableAddString(StringTable, param.ParameterName)
            StringTableAddString(StringTable, f"{param.ParameterName}-{mat.name}")
        for param in mat.ge3mdl_material.PX_CSTS.Parameters:
            StringTableAddString(StringTable, param.ParameterName)
            StringTableAddString(StringTable, f"{param.ParameterName}-{mat.name}")

        for samp in mat.ge3mdl_material.VX_SAMP.Samplers:
            StringTableAddString(StringTable, samp.SamplerName)
            StringTableAddString(StringTable, samp.TexturePath)
            StringTableAddString(StringTable, f"{samp.SamplerName}-sampler-{mat.name}")
        for samp in mat.ge3mdl_material.PX_SAMP.Samplers:
            StringTableAddString(StringTable, samp.SamplerName)
            StringTableAddString(StringTable, samp.TexturePath)
            StringTableAddString(StringTable, f"{samp.SamplerName}-sampler-{mat.name}")

    if Armature is not None:
        for bone in Armature.data.bones:
            StringTableAddString(StringTable, bone.name)

    f.write(b'STRB')
    f.write(struct.pack('<I', 0 ))
    StringTableStart = f.tell()
    f.write(struct.pack('<I', len(StringTable)))
    f.write(b'STRL')
    f.write(struct.pack('<I', 0 ))
    StringTableStringsStart = f.tell()
    for str in StringTable:
        f.write(str.encode('utf-8') + b'\x00')
    while (f.tell() % 4 != 0):
        f.write(b'\x00')
    pos = f.tell()
    f.seek(StringTableStart - 4)
    f.write(struct.pack('<I', pos - StringTableStart))
    f.seek(StringTableStringsStart - 4)
    f.write(struct.pack('<I', pos - StringTableStringsStart))
    f.seek(pos)

    #DSNA section
    f.write(b'DSNA')
    f.write(struct.pack('<I', 8 ))
    f.write(struct.pack('<I', StringTable.index(ModelName) ))
    f.write(struct.pack('<I', StringTable.index(SceneName) ))

    for i in range(len(TRSPs)):
        f.write(b'TRSP')
        f.write(struct.pack('<II', 32, i ))
        f.write(struct.pack('<IIIIIII', TRSPs[i][0].CullBackfaces, TRSPs[i][0].Prop0x10, TRSPs[i][0].UseAlpha, TRSPs[i][0].Prop0x18, TRSPs[i][0].Prop0x1C, TRSPs[i][0].Prop0x20, TRSPs[i][0].Prop0x24) )

    for i in range(len(EFFEs)):
        f.write(b'EFFE')
        f.write(struct.pack('<II', 48, i ))
        f.write(struct.pack('<I', StringTable.index(f"{EFFEs[i][1].name}-fx")))
        f.write(struct.pack('<I', StringTable.index(EFFEs[i][0].ShaderName)))
        f.write(struct.pack('<I', StringTable.index(f"{EFFEs[i][1].name}-fx")))
        f.write(b'TPAS')
        f.write(struct.pack('<Iii', 24, -1, -1 ))
        f.write(struct.pack('<I', TRSPs.index((Mats[i].ge3mdl_material.TRSP, Mats[i]))))
        f.write(struct.pack('<I', StringTable.index(f"{EFFEs[i][1].name}-fx")))
        f.write(struct.pack('<I', StringTable.index(f"{EFFEs[i][1].name}-fx")))
        f.write(struct.pack('<i', -1 ))

    for i in range(len(CSTSs)):
        f.write(b'CSTS')
        f.write(struct.pack('<I', 0))
        CSTSStart = f.tell()
        f.write(struct.pack('<I', i))
        for CSTV in CSTSs[i][0].Parameters:
            f.write(b'CSTV')
            f.write(struct.pack('<I', 8))
            f.write(struct.pack('<I', StringTable.index(CSTV.ParameterName)))
            f.write(struct.pack('<I', StringTable.index(f"{CSTV.ParameterName}-{CSTSs[i][1].name}")))
        pos = f.tell()
        f.seek(CSTSStart - 4)
        f.write(struct.pack('<I', pos - CSTSStart))
        f.seek(pos)

    for i in range(len(SAMPs)):
        f.write(b'SAMP')
        f.write(struct.pack('<I', 0))
        SAMPStart = f.tell()
        f.write(struct.pack('<I', i))
        for SSTV in SAMPs[i][0].Samplers:
            f.write(b'SSTV')
            f.write(struct.pack('<I', 12))
            f.write(struct.pack('<I', StringTable.index(SSTV.SamplerName)))
            f.write(struct.pack('<I', StringTable.index(SSTV.TexturePath)))
            f.write(struct.pack('<I', StringTable.index(f"{SSTV.SamplerName}-sampler-{SAMPs[i][1].name}")))
        pos = f.tell()
        f.seek(SAMPStart - 4)
        f.write(struct.pack('<I', pos - SAMPStart))
        f.seek(pos)

    for i in range(len(Mats)):
        f.write(b'MATE')
        f.write(struct.pack('<II', 32, i ))
        f.write(struct.pack('<I', StringTable.index(Mats[i].name)))
        f.write(struct.pack('<I', StringTable.index(Mats[i].name))) #This should technically be a different name but i don't know if that matters
        f.write(struct.pack('<I', EFFEs.index((Mats[i].ge3mdl_material.EFFE, Mats[i]))))
        #Writing the IDs for other sections, or -1 if unused
        if Mats[i].ge3mdl_material.has_VX_CSTS:
            f.write(struct.pack('<I', CSTSs.index((Mats[i].ge3mdl_material.VX_CSTS, Mats[i]))))
        else:
            f.write(struct.pack('<i', -1))
        if Mats[i].ge3mdl_material.has_VX_SAMP:
            f.write(struct.pack('<I', SAMPs.index((Mats[i].ge3mdl_material.VX_SAMP, Mats[i]))))
        else:
            f.write(struct.pack('<i', -1))

        if Mats[i].ge3mdl_material.has_PX_CSTS:
            f.write(struct.pack('<I', CSTSs.index((Mats[i].ge3mdl_material.PX_CSTS, Mats[i]))))
        else:
            f.write(struct.pack('<i', -1))
        if Mats[i].ge3mdl_material.has_PX_SAMP:
            f.write(struct.pack('<I', SAMPs.index((Mats[i].ge3mdl_material.PX_SAMP, Mats[i]))))
        else:
            f.write(struct.pack('<i', -1))

    f.write(b'VARI')
    f.write(struct.pack('<I', 0))
    VARIStart = f.tell()
    f.write(struct.pack('<I', 0))
    f.write(struct.pack('<I', StringTable.index("Default")))
    f.write(struct.pack('<ii', -1, -1))
    for obj in exportable_objects:
        #for MORP section we only write prims for the morphs
        if bisMorph:
            if obj.data.shape_keys is not None and len(obj.data.shape_keys.key_blocks) > 1:
                for morph in obj.data.shape_keys.key_blocks:
                    if morph.name == "Basic":
                        continue
                    f.write(b'PRIM')
                    f.write(struct.pack('<I', 28))
                    f.write(struct.pack('<I', SAMPs.index((obj.active_material.ge3mdl_material.PX_SAMP, obj.active_material))))
                    #Face Morphs are handled by a very uncool un unique way to be a pain 
                    if "Brow" in morph.name:
                         f.write(struct.pack('<I', StringTable.index("mesh_Brow_mesh-morph")))
                    elif "Mouth" in morph.name:
                        f.write(struct.pack('<I', StringTable.index("mesh_Mouth_mesh-morph")))
                    elif "Eye" in morph.name:
                        f.write(struct.pack('<I', StringTable.index("mesh_Eye_mesh-morph")))
                    else:
                        f.write(struct.pack('<I', StringTable.index(morph.name)))
                    f.write(struct.pack('<I', StringTable.index(obj.active_material.name.replace("_mat", "_sg")))) #This should technically be a different name but i don't know if that matters
                    f.write(struct.pack('<I', 0))
                    f.write(struct.pack('<I', StringTable.index(morph.name))) #Might be different from first name but sometimes isn't one is probably the binding name
                    f.write(struct.pack('<I', Mats.index(obj.active_material)))
                    f.write(struct.pack('<I', crc32_bzip2(obj.name.encode('utf-8'))))  #Face Morph Hash id, find a way to handle morph exporting
        else:
            f.write(b'PRIM')
            f.write(struct.pack('<I', 28))
            f.write(struct.pack('<I', SAMPs.index((obj.active_material.ge3mdl_material.PX_SAMP, obj.active_material))))    #SAMPs are also written here but i think it's useless? while bind them anyways
            f.write(struct.pack('<I', StringTable.index(obj.name)))
            f.write(struct.pack('<I', StringTable.index(obj.active_material.name.replace("_mat", "_sg")))) #This should technically be a different name but i don't know if that matters
            f.write(struct.pack('<I', 0))
            f.write(struct.pack('<I', StringTable.index(obj.name))) #Might be different from first name but sometimes isn't one is probably the binding name
            f.write(struct.pack('<I', Mats.index(obj.active_material)))
            f.write(struct.pack('<i', -1))  #Face Morph Hash id, find a way to handle morph exporting
    pos = f.tell()
    f.seek(VARIStart - 4)
    f.write(struct.pack('<I', pos - VARIStart))
    f.seek(pos)

    if Armature is not None:
        f.write(b'BONE')
        f.write(struct.pack('<I', 72 * len(Armature.data.bones) + 4 ))
        f.write(struct.pack('<I', 0))

        for i in range(len(Armature.data.bones)):
            f.write(b'BOIF')
            f.write(struct.pack('<I', 8))
            f.write(struct.pack('<I', StringTable.index(Armature.data.bones[i].name)))
            f.write(struct.pack('<I', i))

        for bone in Armature.data.bones:
            f.write(b'IMTX')
            f.write(struct.pack('<I', 48))
            mat = bone.matrix_local.inverted()
            f.write(struct.pack('<ffff', mat[0][0], mat[0][1], mat[0][2], mat[0][3]))
            f.write(struct.pack('<ffff', mat[1][0], mat[1][1], mat[1][2], mat[1][3]))
            f.write(struct.pack('<ffff', mat[2][0], mat[2][1], mat[2][2], mat[2][3]))

    pos = f.tell()
    totalSize = f.tell() - sectionStart
    f.seek(sectionStart - 4)
    f.write(struct.pack('<I', totalSize ))
    f.seek(pos)
    return totalSize + 8

def WriteGPRString(f: io.BytesIO, string, StringTableStream: io.BytesIO, StringTableMap):
    if string in StringTableMap:
        f.write(struct.pack('<I', StringTableMap[string]))
    else:
        f.write(struct.pack('<I', StringTableStream.tell()))
        StringTableMap[string] = StringTableStream.tell()
        StringTableStream.write(string.encode('utf-8') + b'\x00')

def writeVXAR(self, context, f, obj, StringTableStream, Buffer1Stream, StringTableMap):
    f.write(struct.pack('<I', 0))
    f.write(struct.pack('<I', Buffer1Stream.tell()))

    BufferStart = Buffer1Stream.tell()
    VertexStride = 0

    if self.exportplatform == "DX11":
        if ShaderInfoLoad is False:
            loadShaderInfo()
        Shader = obj.active_material.ge3mdl_material.EFFE.ShaderName
        Attributes = ShaderInfo[Shader]
        Buffer1Stream.write(struct.pack('<I', len(Attributes) - 1))
        for att in Attributes:
            if att == "POSITION" or att == "NORMAL":
                Buffer1Stream.write(struct.pack('<IIII', VertexStride, 0, 12, 6))
                VertexStride = VertexStride + 12
            if att == "TEXCOORD":
                Buffer1Stream.write(struct.pack('<IIII', VertexStride, 0, 4, 34))
                VertexStride = VertexStride + 4
            if att == "TANGENT" or att == "BINORMAL":
                Buffer1Stream.write(struct.pack('<IIII', VertexStride, 0, 4, 31))
                VertexStride = VertexStride + 4
            if att == "BLENDWEIGHT" or att == "COLOR":
                Buffer1Stream.write(struct.pack('<IIII', VertexStride, 0, 4, 28))
                VertexStride = VertexStride + 4
            if att == "BLENDINDICES":
                Buffer1Stream.write(struct.pack('<IIII', VertexStride, 0, 4, 30))
                VertexStride = VertexStride + 4
    elif self.exportplatform == "NX":
        ...
    else:
        self.report({'ERROR'}, "Unknown export platform set")

    while (Buffer1Stream.tell() % 16 != 0):
            Buffer1Stream.write(b'\x00')
    f.write(struct.pack('<I', Buffer1Stream.tell() -  BufferStart))
    f.write(struct.pack('<iII', -1, 0, 1))

    return VertexStride

def writeIXBF(self, context, f, obj, StringTableStream: io.BytesIO, Buffer1Stream: io.BytesIO, Buffer2Stream: io.BytesIO, StringTableMap: dict, Shape):
    f.write(struct.pack('<I', 0))
    f.write(struct.pack('<I', Buffer1Stream.tell()))
    f.write(struct.pack('<I', 16)) #Size of VXBO, always 16
    f.write(struct.pack('<I', Buffer2Stream.tell()))
    Shape["IXBF"] = Buffer1Stream.tell()

    depsgraph = bpy.context.evaluated_depsgraph_get()
    mesh_eval = obj.evaluated_get(depsgraph).to_mesh()
    BufferStart = Buffer2Stream.tell()
    FaceCount = 0
    for tri in mesh_eval.loop_triangles:
        for vert in tri.vertices:
            if len(mesh_eval.vertices) > 65535:
                Buffer2Stream.write(struct.pack('<I', vert))
            else:
                Buffer2Stream.write(struct.pack('<H', vert))
            FaceCount = FaceCount + 1
    Shape["IXBFCount"] = FaceCount
    f.write(struct.pack('<I', Buffer2Stream.tell() - BufferStart))
    f.write(struct.pack('<I', 0))
    while (Buffer2Stream.tell() % 16 != 0):
        Buffer2Stream.write(b'\x00')
    Buffer1Stream.write(struct.pack('<IIII', 0, 0 , 57, 0))

def writeVXBF(self, context, f: io.BytesIO, obj, VertexStride, StringTableStream: io.BytesIO, Buffer1Stream: io.BytesIO, Buffer2Stream: io.BytesIO, StringTableMap: dict, MorphName = None):
    f.write(b'VXBF')
    if MorphName is not None:
        WriteGPRString(f, MorphName, StringTableStream, StringTableMap)
    else:
        WriteGPRString(f, obj.name, StringTableStream, StringTableMap)
    f.write(struct.pack('<I', 0))
    f.write(struct.pack('<II', Buffer1Stream.tell(), 16))

    #edgemod = obj.modifiers.new(name="EdgeSplitBySharp", type="EDGE_SPLIT")
    #edgemod.use_edge_angle = True
    #edgemod.use_edge_sharp = True

    depsgraph = bpy.context.evaluated_depsgraph_get()

    obj_eval = obj.evaluated_get(depsgraph)
    mesh_eval = obj_eval.to_mesh()
    mesh_eval.update()

    f.write(struct.pack('<II', Buffer2Stream.tell(),  len(mesh_eval.vertices)*VertexStride ))
    f.write(struct.pack('<I', 0))
    Buffer1Stream.write(struct.pack('<IIII', 0, 0, len(mesh_eval.vertices), VertexStride))

    #Preprocess all the vertex data so we can pack it all in one pass
    Vertices= []
    armature = None
    for mod in obj.modifiers:
        if mod.type == 'ARMATURE' and mod.object:
            armature = mod.object
            break
    if armature is not None:
        bone_index_by_name = {
            bone.name: i
            for i, bone in enumerate(armature.data.bones)
        }
    else:
        bone_index_by_name = {}

    #verts can only have 1 position and normal so we don't have to worry about packing multiple
    for i in range(len(mesh_eval.vertices)):
        vert = mesh_eval.vertices[i]
        VertexData = {}
        if MorphName is not None:
            VertexData["POSITION"] = obj_eval.data.shape_keys.key_blocks[MorphName].data[i].co
        else:
            VertexData["POSITION"] = vert.co
        VertexData["BLENDINDICES"] = []
        VertexData["BLENDWEIGHT"] = []
        VertexData["TEXCOORD"] = []
        VertexData["COLOR"] = []
        for group in vert.groups:
            group_name = obj.vertex_groups[group.group].name
            weight = group.weight
            if weight <= 0.0:
                continue
            if group_name in bone_index_by_name:
                VertexData["BLENDINDICES"].append(bone_index_by_name.get(group_name))
                VertexData["BLENDWEIGHT"].append(weight)
        Vertices.append(VertexData)

    for uv_layer in mesh_eval.uv_layers:
        for poly in mesh_eval.polygons:
            for loop_index in poly.loop_indices:
                vert_index = mesh_eval.loops[loop_index].vertex_index
                uv_coords = uv_layer.data[loop_index].uv
                Vertices[vert_index]["TEXCOORD"].append(uv_coords)

    for color in mesh_eval.color_attributes:
        for i in range(len(color.data)):
            Vertices[i]["COLOR"].append((color.data[i].color[0], color.data[i].color[1], color.data[i].color[2], color.data[i].color[3]))

    mesh_eval.calc_tangents(uvmap=mesh_eval.uv_layers[0].name)
    hasCustomNormals = False
    if mesh_eval.attributes.get("custom_normal") is not None:
        hasCustomNormals = True
    for poly in mesh_eval.polygons:
        for loop_index in poly.loop_indices:
            loop = mesh_eval.loops[loop_index]
            vert_index = loop.vertex_index
            #if hasCustomNormals:
            #    packed_normal = mesh_eval.attributes["custom_normal"].data[loop_index]
            #    if packed_normal.value[0] == 0 and packed_normal.value[1] == 0:
            #        normal = loop.normal.copy()
            #    else:
            #        normal = mathutils.Vector(unpack_16bit_normal(packed_normal.value[0], packed_normal.value[1]))
            #else:
            normal = loop.normal.copy()
            tangent = loop.tangent.copy()
            bitangent = loop.bitangent_sign * normal.cross(tangent)

            Vertices[vert_index]["NORMAL"] = normal
            Vertices[vert_index]["TANGENT"] = tangent
            Vertices[vert_index]["BINORMAL"] = bitangent
            
    mesh_eval.free_tangents()

    BufferStart = Buffer1Stream.tell()
    if self.exportplatform == "DX11":
        if ShaderInfoLoad is False:
            loadShaderInfo()
        Shader = obj.active_material.ge3mdl_material.EFFE.ShaderName
        Attributes = ShaderInfo[Shader]
        for vert in Vertices:
            Texcoord_index = 0
            Color_index = 0
            for att in Attributes:  #Since a buffer can be packed in dynamic ways we'll have check which attribute the shader wants packed where
                if att == "POSITION":
                    Buffer2Stream.write(struct.pack('<fff', vert["POSITION"].x, vert["POSITION"].y, vert["POSITION"].z))
                if att == "NORMAL":
                    Buffer2Stream.write(struct.pack('<fff', vert["NORMAL"].x, vert["NORMAL"].y, vert["NORMAL"].z))
                if att == "TEXCOORD":
                    Buffer2Stream.write(struct.pack('<ee', vert["TEXCOORD"][Texcoord_index][0], vert["TEXCOORD"][Texcoord_index][1]))
                    Texcoord_index = Texcoord_index + 1
                if att == "TANGENT":
                    Buffer2Stream.write(struct.pack('<bbbb', int(clamp(vert["TANGENT"].x * 127, -128, 127)), int(clamp(vert["TANGENT"].y * 127, -128, 127)), int(clamp(vert["TANGENT"].z * 127, -128, 127)), 127))
                    #Buffer2Stream.write(struct.pack('<BBBB', 127, 127, 127, 127))
                if att == "BINORMAL":
                    Buffer2Stream.write(struct.pack('<bbbb', int(clamp(vert["BINORMAL"].x * 127, -128, 127)), int(clamp(vert["BINORMAL"].y * 127, -128, 127)), int(clamp(vert["BINORMAL"].z * 127, -128, 127)), 127))
                    #Buffer2Stream.write(struct.pack('<BBBB', 127, 127, 127, 127))
                if att == "BLENDINDICES":
                    for idx in range(4):
                        try:
                            Buffer2Stream.write(struct.pack('<B', vert["BLENDINDICES"][idx]))
                        except:
                            Buffer2Stream.write(struct.pack('<B', 0))
                if att == "BLENDWEIGHT":
                    normalized_weights = custom_normalize(vert["BLENDWEIGHT"])
                    for idx in range(4):
                        try:
                            Buffer2Stream.write(struct.pack('<B', int(normalized_weights[idx])))
                        except:
                            Buffer2Stream.write(struct.pack('<B', 0))
                if att == "COLOR":
                    Buffer2Stream.write(struct.pack('<BBBB', int(vert["COLOR"][Color_index][0] * 255), int(vert["COLOR"][Color_index][1] * 255), int(vert["COLOR"][Color_index][2]) * 255, int(vert["COLOR"][Color_index][3] * 255)))
                    Color_index = Color_index + 1
    elif self.exportplatform == "NX":
        ...
    else:
        self.report({'ERROR'}, "Unknown export platform set")

    
    while (Buffer2Stream.tell() % 16 != 0):
            Buffer2Stream.write(b'\x00')

    return

def writeGPR(self, context, f: io.IOBase, exportable_objects, Scene):
    GPRStart = f.tell()
    f.write(b'GPR\x00')
    f.write(struct.pack('<I', 0))
    if self.exportplatform == "DX11":
        f.write(b'DX11')
    elif self.exportplatform == "NX":
        f.write(b'NX\x00\x00')
    else:
        self.report({'ERROR'}, "Unknown export platform set")

    f.write(struct.pack('<I', 0)) #size but i'm not sure which what, model can load without it
    SectionStart = f.tell()
    f.write(struct.pack('<BBBBII', 1, 16, 8, 32, 48, 48))
    f.write(struct.pack('<I', 0)) #Relative pointer to after Buffer 1, based of the end of this header
    f.write(struct.pack('<iI', -1, 0))
    f.write(struct.pack('<II', 0, 0)) #Buffer 2 relative offset, based off section start and Buffer 2 size
    f.write(struct.pack('<iIII', -1, 0, 0, 0))
    HeaderEnd = f.tell()

    f.write(b'HEAP')
    f.write(struct.pack('<II', 0, 32))
    HEAPSizes = f.tell()
    f.write(struct.pack('<IIIII', 0, 0, 0, 0, 0)) #Sizes we'll write later(3), unknown 0, and descriptor count

    #Using streams so that it's easy to calculate the local offset of each buffer
    StringTableStream = io.BytesIO()
    Buffer1Stream = io.BytesIO()
    Buffer2Stream = io.BytesIO()
    StringTableMap = {}
    DesCount = 0
    Mats = []
    Shapes = []     #Store the offsets and magic of the sections will need for the VXST
    VXSBs = []
    PXSBs = []
    MorphObjects = []

    #Start the main data writing, writing descriptors stright to the file and their data/strings to a buffer
    #all these loops are kinda gross but i want to put the data back in it's original ordering incase of issues 

    #First pass, write the VXBO, VXAR, IXBF, and VXBF of each object
    for obj in exportable_objects:
        splitmod = None
        TempSplit = False
        for mod in obj.modifiers:
            if mod.type == 'NODES':
                if mod.node_group == bpy.data.node_groups["GE3MeshSplit"]:
                    splitmod = mod
                    break
        if splitmod == None:
            TempSplit = True
            splitmod = obj.modifiers.new(f"GE3Spliter-Temp", type='NODES')
            splitmod.node_group = bpy.data.node_groups["GE3MeshSplit"]
            splitmod["Socket_2"] = obj.data.uv_layers[0].name
            splitmod["Socket_3"] = True
            splitmod["Socket_4"] = True

        if obj.active_material not in Mats:
            Mats.append(obj.active_material)
        Shape = {}
        Shape["Name"] = obj.name
        f.write(b'VXBO')
        WriteGPRString(f, obj.name, StringTableStream, StringTableMap)
        f.write(struct.pack('<I', 0))
        f.write(struct.pack('<I', Buffer1Stream.tell()))
        f.write(struct.pack('<I', 112)) #Size of VXBO, always 112
        f.write(struct.pack('<iII', -1, 0, 1))
        Shape["VXBO"] = Buffer1Stream.tell()
        Buffer1Stream.write(struct.pack('<28f', *[0] * 28))

        Shape["VXAR"] = Buffer1Stream.tell()
        f.write(b'VXAR')
        WriteGPRString(f, obj.name, StringTableStream, StringTableMap)
        VertexStride = writeVXAR(self, context, f, obj, StringTableStream, Buffer1Stream, StringTableMap)

        #Write index buffer
        f.write(b'IXBF')
        WriteGPRString(f, obj.name, StringTableStream, StringTableMap)
        writeIXBF(self, context, f, obj, StringTableStream, Buffer1Stream, Buffer2Stream, StringTableMap, Shape)

        #Write Vertex buffer
        Shape["VXBF"] = Buffer1Stream.tell()
        writeVXBF(self, context, f, obj, VertexStride, StringTableStream, Buffer1Stream, Buffer2Stream, StringTableMap)

        Shapes.append(Shape)
        DesCount = DesCount + 4

        #check if the mesh has any shape keys, these will all be written after the base mesh
        if obj.data.shape_keys is not None and len(obj.data.shape_keys.key_blocks) > 1:
            MorphObjects.append(obj)

        if TempSplit:
            obj.modifiers.remove(splitmod)

    for obj in MorphObjects:
        for morph in obj.data.shape_keys.key_blocks:
            if morph.name == "Basic":
                continue

            Shape = {}
            Shape["Name"] = morph.name
            f.write(b'VXBO')
            WriteGPRString(f, morph.name, StringTableStream, StringTableMap)
            f.write(struct.pack('<I', 0))
            f.write(struct.pack('<I', Buffer1Stream.tell()))
            f.write(struct.pack('<I', 112)) #Size of VXBO, always 112
            f.write(struct.pack('<iII', -1, 0, 1))
            Shape["VXBO"] = Buffer1Stream.tell()
            Buffer1Stream.write(struct.pack('<28f', *[0] * 28))

            Shape["VXAR"] = Buffer1Stream.tell()
            f.write(b'VXAR')
            WriteGPRString(f, morph.name, StringTableStream, StringTableMap)
            VertexStride = writeVXAR(self, context, f, obj, StringTableStream, Buffer1Stream, StringTableMap)

            #Write index buffer
            f.write(b'IXBF')
            WriteGPRString(f, morph.name, StringTableStream, StringTableMap)
            writeIXBF(self, context, f, obj, StringTableStream, Buffer1Stream, Buffer2Stream, StringTableMap, Shape)

            #Write Vertex buffer
            Shape["VXBF"] = Buffer1Stream.tell()
            writeVXBF(self, context, f, obj, VertexStride, StringTableStream, Buffer1Stream, Buffer2Stream, StringTableMap, morph.name)
    
            Shapes.append(Shape)
            DesCount = DesCount + 4

    #Second pass, write all the VXTS shapes
    for Shape in Shapes:
        f.write(b'VXST')
        WriteGPRString(f, Shape["Name"], StringTableStream, StringTableMap)
        f.write(struct.pack('<I', 0))
        f.write(struct.pack('<I', Buffer1Stream.tell()))
        f.write(struct.pack('<I', 80))
        f.write(struct.pack('<iII', -1, 0, 1))

        Buffer1Stream.write(struct.pack('<III', 0, 0, 0))
        Buffer1Stream.write(struct.pack('<I', Shape["VXBO"]))
        Buffer1Stream.write(struct.pack('<I', 4))
        Buffer1Stream.write(struct.pack('<I', Shape["IXBFCount"]))
        Buffer1Stream.write(struct.pack('<I', Shape["IXBF"]))
        Buffer1Stream.write(struct.pack('<I', 1))
        Buffer1Stream.write(struct.pack('<iiii', -1, -1, -1, -1))
        Buffer1Stream.write(struct.pack('<ffff', 1, 0, 0, 1))
        Buffer1Stream.write(struct.pack('<II', 0, 0))
        Buffer1Stream.write(struct.pack('<I', Shape["VXAR"]))
        Buffer1Stream.write(struct.pack('<I', Shape["VXBF"]))
        DesCount = DesCount + 1

    #Third pass, write Vertex Shader data, SHMI, VXSH, SHBI
    for mat in Mats:
        if mat.ge3mdl_material.dataImported == False:
            self.report({'WARNING'}, f"Material {mat.name} is missing GE3 shader info")
            continue

        VXSB = {}
        f.write(b'SHMI')
        WriteGPRString(f, f"{mat.name}-fx", StringTableStream, StringTableMap)
        f.write(struct.pack('<I', 0))
        f.write(struct.pack('<I', Buffer1Stream.tell()))
        f.write(struct.pack('<I', 32))
        f.write(struct.pack('<iII', -1, 0, 1))
        Buffer1Stream.write(struct.pack('<IIII', 0, 0, 0, 0))
        WriteGPRString(Buffer1Stream, "", StringTableStream, StringTableMap)
        Buffer1Stream.write(struct.pack('<iiI', -1, -1, 0))

        f.write(b'VXSH')
        WriteGPRString(f, f"{mat.name}-fx", StringTableStream, StringTableMap)
        f.write(struct.pack('<I', 0))
        f.write(struct.pack('<I', Buffer1Stream.tell()))
        VXSB["VXSH"] = Buffer1Stream.tell()

        BufferStart = Buffer1Stream.tell()
        VXSH = mat.ge3mdl_material.VXSB.XXSH
        Buffer1Stream.write(struct.pack('<IIIIII', 0, 0, 0, 0, 0, 0))
        Buffer1Stream.write(struct.pack('<I', len(VXSH.Parameters)))
        Buffer1Stream.write(struct.pack('<I', 0))
        for parameter in VXSH.Parameters:
            WriteGPRString(Buffer1Stream, parameter.ParameterName, StringTableStream, StringTableMap)
            Buffer1Stream.write(struct.pack('<I', parameter.ParameterOffset))
            Buffer1Stream.write(struct.pack('<I', parameter.bl_rna.properties["ParameterType"].enum_items[parameter.ParameterType].value))
            Buffer1Stream.write(struct.pack('<I', parameter.ParameterSize))
        f.write(struct.pack('<I', Buffer1Stream.tell() - BufferStart))
        f.write(struct.pack('<iII', -1, 0, 1))

        #VXSH only has one SHBI section that i know of
        if mat.ge3mdl_material.VXSB.has_shbi_1:
            f.write(b'SHBI')
            WriteGPRString(f, f"{mat.name}-fx", StringTableStream, StringTableMap)
            f.write(struct.pack('<I', 0))
            f.write(struct.pack('<I', Buffer1Stream.tell()))
            VXSB["SHBI1"] = Buffer1Stream.tell()
            BufferStart = Buffer1Stream.tell()
            SHBI = mat.ge3mdl_material.VXSB.SHBI1
            Buffer1Stream.write(struct.pack('<IIII', 0, 0, 0, 0))
            Buffer1Stream.write(struct.pack('<I', len(SHBI.Parameters)))
            Buffer1Stream.write(struct.pack('<I', 0))
            for parameter in SHBI.Parameters:
                WriteGPRString(Buffer1Stream, parameter.ParameterName, StringTableStream, StringTableMap)
                Buffer1Stream.write(struct.pack('<I', parameter.ParameterOffset))
                Buffer1Stream.write(struct.pack('<I', parameter.ParameterSize))
            while (Buffer1Stream.tell() % 16 != 0):
                Buffer1Stream.write(b'\x00')
            f.write(struct.pack('<I', Buffer1Stream.tell() - BufferStart))
            f.write(struct.pack('<iII', -1, 0, 1))
            DesCount = DesCount + 1

        VXSBs.append(VXSB)
        DesCount = DesCount + 2

    #Fouth Pass, Write the PXSH their SHBI
    for mat in Mats:
        if mat.ge3mdl_material.dataImported == False:
            self.report({'WARNING'}, f"Material {mat.name} is missing GE3 shader info")
            continue

        PXSB = {}
        f.write(b'PXSH')
        WriteGPRString(f, f"{mat.name}-fx", StringTableStream, StringTableMap)
        f.write(struct.pack('<I', 0))
        f.write(struct.pack('<I', Buffer1Stream.tell()))

        PXSB["PXSH"] = Buffer1Stream.tell()
        BufferStart = Buffer1Stream.tell()
        PXSH = mat.ge3mdl_material.PXSB.XXSH
        Buffer1Stream.write(struct.pack('<IIIIII', 0, 0, 0, 0, 0, 0))
        Buffer1Stream.write(struct.pack('<I', len(PXSH.Parameters)))
        Buffer1Stream.write(struct.pack('<I', 0))
        for parameter in PXSH.Parameters:
            WriteGPRString(Buffer1Stream, parameter.ParameterName, StringTableStream, StringTableMap)
            Buffer1Stream.write(struct.pack('<I', parameter.ParameterOffset))
            Buffer1Stream.write(struct.pack('<I', parameter.bl_rna.properties["ParameterType"].enum_items[parameter.ParameterType].value))
            Buffer1Stream.write(struct.pack('<I', parameter.ParameterSize))
        f.write(struct.pack('<I', Buffer1Stream.tell() - BufferStart))
        f.write(struct.pack('<iII', -1, 0, 0))
        DesCount = DesCount + 1

        if mat.ge3mdl_material.PXSB.has_shbi_1:
            f.write(b'SHBI')
            WriteGPRString(f, f"{mat.name}-fx", StringTableStream, StringTableMap)
            f.write(struct.pack('<I', 0))
            f.write(struct.pack('<I', Buffer1Stream.tell()))
            PXSB["SHBI1"] = Buffer1Stream.tell()
            BufferStart = Buffer1Stream.tell()
            SHBI = mat.ge3mdl_material.PXSB.SHBI1
            Buffer1Stream.write(struct.pack('<IIII', 0, 0, 0, 0))
            Buffer1Stream.write(struct.pack('<I', len(SHBI.Parameters)))
            Buffer1Stream.write(struct.pack('<I', 0))
            for parameter in SHBI.Parameters:
                WriteGPRString(Buffer1Stream, parameter.ParameterName, StringTableStream, StringTableMap)
                Buffer1Stream.write(struct.pack('<I', parameter.ParameterOffset))
                Buffer1Stream.write(struct.pack('<I', parameter.ParameterSize))
            while (Buffer1Stream.tell() % 16 != 0):
                Buffer1Stream.write(b'\x00')
            f.write(struct.pack('<I', Buffer1Stream.tell() - BufferStart))
            f.write(struct.pack('<iII', -1, 0, 1))
            DesCount = DesCount + 1

        if mat.ge3mdl_material.PXSB.has_shbi_2:
            f.write(b'SHBI')
            WriteGPRString(f, f"{mat.name}-fx", StringTableStream, StringTableMap)
            f.write(struct.pack('<I', 0))
            f.write(struct.pack('<I', Buffer1Stream.tell()))
            PXSB["SHBI2"] = Buffer1Stream.tell()
            BufferStart = Buffer1Stream.tell()
            SHBI = mat.ge3mdl_material.PXSB.SHBI2
            Buffer1Stream.write(struct.pack('<IIII', 0, 0, 0, 0))
            Buffer1Stream.write(struct.pack('<I', len(SHBI.Parameters)))
            Buffer1Stream.write(struct.pack('<I', 0))
            for parameter in SHBI.Parameters:
                WriteGPRString(Buffer1Stream, parameter.ParameterName, StringTableStream, StringTableMap)
                Buffer1Stream.write(struct.pack('<I', parameter.ParameterOffset))
                Buffer1Stream.write(struct.pack('<I', parameter.ParameterSize))
            while (Buffer1Stream.tell() % 16 != 0):
                Buffer1Stream.write(b'\x00')
            f.write(struct.pack('<I', Buffer1Stream.tell() - BufferStart))
            f.write(struct.pack('<iII', -1, 0, 1))
            DesCount = DesCount + 1

        PXSBs.append(PXSB)

    #Fifth pass, SHCO
    for mat in Mats:
        if mat.ge3mdl_material.dataImported == False:
            self.report({'WARNING'}, f"Material {mat.name} is missing GE3 shader info")
            continue

        #These need to be in order according to the shader
        SCHOs = mat.ge3mdl_material.Constants.SHCOs
        for shco in SCHOs:
            f.write(b'SHCO')
            WriteGPRString(f, f"{shco.Name}-{mat.name}", StringTableStream, StringTableMap)
            f.write(struct.pack('<I', 0))
            f.write(struct.pack('<I', Buffer1Stream.tell()))
            f.write(struct.pack('<IiII', 32, -1, 0, 1))

            Buffer1Stream.write(bytes.fromhex(shco.SHCORawData))
            DesCount = DesCount + 1

    #Sixth pass, holy hell i gotta find a better way to do this, anyways now we write the SMST
    for mat in Mats:
        if mat.ge3mdl_material.dataImported == False:
            self.report({'WARNING'}, f"Material {mat.name} is missing GE3 shader info")
            continue

        SMSTs = mat.ge3mdl_material.Constants.SMSTs
        for SMST in SMSTs:
            f.write(b'SMST')
            WriteGPRString(f, f"{SMST.Name}-sampler-{mat.name}", StringTableStream, StringTableMap)
            f.write(struct.pack('<I', 0))
            f.write(struct.pack('<I', Buffer1Stream.tell()))
            f.write(struct.pack('<IiII', 32, -1, 0, 1))

            #These values always seem to be the same
            Buffer1Stream.write(bytes.fromhex(SMST.SMSTRawData))
            DesCount = DesCount + 1
 
    #Seventh pass, write the VXSBs
    for i in range(len(Mats)):
        if Mats[i].ge3mdl_material.dataImported == False:
            self.report({'WARNING'}, f"Material {Mats[i].name} is missing GE3 shader info")
            continue

        f.write(b'VXSB')
        WriteGPRString(f, f"{Mats[i].name}-fx", StringTableStream, StringTableMap)
        f.write(struct.pack('<I', 0))
        f.write(struct.pack('<I', Buffer1Stream.tell()))
        f.write(struct.pack('<IiII', 32, -1, 0, 1))

        Buffer1Stream.write(struct.pack('<II', 0, 0))
        Buffer1Stream.write(struct.pack('<I', VXSBs[i]["VXSH"]))
        if "SHBI1" in VXSBs[i]:
            Buffer1Stream.write(struct.pack('<I', VXSBs[i]["SHBI1"]))
        else:
            Buffer1Stream.write(struct.pack('<i', -1))
        if "SHBI2" in VXSBs[i]:
            Buffer1Stream.write(struct.pack('<I', VXSBs[i]["SHBI2"]))
        else:
            Buffer1Stream.write(struct.pack('<i', -1))
        Buffer1Stream.write(struct.pack('<III', 0, 0, 0))
        DesCount = DesCount + 1

    #Eighth and final pass, thank god, write the PXSBs
    for i in range(len(Mats)):
        if Mats[i].ge3mdl_material.dataImported == False:
            self.report({'WARNING'}, f"Material {Mats[i].name} is missing GE3 shader info")
            continue

        f.write(b'PXSB')
        WriteGPRString(f, f"{Mats[i].name}-fx", StringTableStream, StringTableMap)
        f.write(struct.pack('<I', 0))
        f.write(struct.pack('<I', Buffer1Stream.tell()))
        f.write(struct.pack('<IiII', 32, -1, 0, 1))

        Buffer1Stream.write(struct.pack('<II', 0, 0))
        Buffer1Stream.write(struct.pack('<I', PXSBs[i]["PXSH"]))
        if "SHBI1" in PXSBs[i]:
            Buffer1Stream.write(struct.pack('<I', PXSBs[i]["SHBI1"]))
        else:
            Buffer1Stream.write(struct.pack('<i', -1))
        if "SHBI2" in PXSBs[i]:
            Buffer1Stream.write(struct.pack('<I', PXSBs[i]["SHBI2"]))
        else:
            Buffer1Stream.write(struct.pack('<i', -1))
        Buffer1Stream.write(struct.pack('<III', 0, 0, 0))
        DesCount = DesCount + 1


    DesEnd = f.tell()

    if Scene is None:
        ModelName = exportable_objects[0].users_collection[0].name
    else:
        ModelName = Scene.users_collection[0].name

    f.write(StringTableStream.getbuffer())
    f.write(ModelName.encode('utf-8') + b'\x00')
    while (f.tell() % 16 != 0):
        f.write(b'\x00')
    StringsEnd = f.tell()

    f.write(Buffer1Stream.getbuffer())
    Buffer1End = f.tell()
    f.write(struct.pack('<IIII', 0, 0, 0, 0))   # There's a weird empty buffer if of a undetermined size, let's just write 16 bytes for the pointer
    while (f.tell() % 16 != 0):
            f.write(b'\x00')

    Buffer2Offset = f.tell()
    f.write(Buffer2Stream.getbuffer())
    while (f.tell() % 64 != 0):
        f.write(b'\x00')

    pos = f.tell()
    f.seek(HEAPSizes)
    f.write(struct.pack('<IIIII', (DesEnd - HeaderEnd), (StringsEnd - HeaderEnd), len(StringTableStream.getbuffer()), 0, DesCount))
    f.seek(SectionStart + 12)
    f.write(struct.pack('<IiIII', (Buffer1End - HeaderEnd), -1, 0, (Buffer2Offset - SectionStart), len(Buffer2Stream.getbuffer())))
    f.seek(pos)

    totalSize = f.tell() - GPRStart
    Buffer1Stream.close()
    Buffer2Stream.close()
    StringTableStream.close()

    return totalSize

def writeNODT(self, context, f):
    return 0

def writeBRNT(self, context, f: io.BytesIO, armature: bpy.types.Object):
    sectionStart = f.tell()
    f.write(b'BRNTREx86Ver2.00')
    f.write(struct.pack('<I', len(armature.data.bones)))
    f.write(struct.pack('<I', len(armature.data.bones)))
    f.write(struct.pack('<II', 0, 0 ))

    bone_index_by_name = {
        bone.name: i
        for i, bone in enumerate(armature.data.bones)
    }

    for bone in armature.data.bones:
        f.write(struct.pack('<I', crc32_bzip2(bone.name.encode('utf-8'))))
        f.write(encode_string_16bytes(bone.name))
        f.write(struct.pack('<H', bone_index_by_name.get(bone.name)))

        if bone.parent is None:
            f.write(struct.pack('<h', -1))
        else:
            f.write(struct.pack('<H', bone_index_by_name.get(bone.parent.name)))

        f.write(struct.pack('<h', -1))
        f.write(struct.pack('<H', bone_index_by_name.get(bone.name)))

        if len(bone.children) > 0:
            f.write(struct.pack('<H', bone_index_by_name.get(bone.children[0].name)))
        else:
            f.write(struct.pack('<h', -1))

        if bone.parent and len(bone.parent.children) > 1 and bone.name != bone.parent.children[-1].name:
            f.write(struct.pack('<h', bone_index_by_name.get(bone.name) + len(bone.children_recursive) + 1))
        else:
            f.write(struct.pack('<h', -1))

        f.write(struct.pack('<h', -256))
        if bone.name.endswith("_BLP"):
            f.write(struct.pack('<BB', 1, 4))
        else:
            f.write(struct.pack('<h', 0))
        f.write(struct.pack('<I', 0))

        bonemat = bone.matrix_local
        euler = bone.matrix.to_3x3().to_euler()
        if bone.parent:
            parent_invert = bone.parent.matrix_local.inverted()
            relative_mat = parent_invert @ bonemat
            trans = relative_mat.to_translation()
        else:
            trans = bone.matrix_local.to_translation()
        scale = bonemat.to_scale()
        f.write(struct.pack('<fff', trans.x, trans.y, trans.z))
        f.write(struct.pack('<fff', 0, 0, 0))
        f.write(struct.pack('<fff', scale.x, scale.y, scale.z))
        f.write(struct.pack('<fff', euler.x, euler.y, euler.z))

    totalSize = f.tell() - sectionStart
    return totalSize

def write60SE(self, context, f: io.BytesIO, armature: bpy.types.Object):
    sectionStart = f.tell()
    f.write(b'60SE')
    f.write(struct.pack('<III', 0, 0, 0 )) #Size to write later
    f.write(struct.pack('<I', len(armature.data.bones)))
    f.write(struct.pack('<I', 1))
    f.write(struct.pack('<IIIIIII', 0, 0, 0, 0, 0, 0, 0 )) #dummy offsets
    f.write(struct.pack('<II', 0,0))

    bones = armature.data.bones
    #write bone parent pairs
    f.write(struct.pack('<I', len(bones))) #first 3 bones are dupped, sometimes more are but it shouldn't matter
    for i in range(len(bones)):
        if i == 0:
            f.write(struct.pack('<HH', i, 32767))
        else:
            f.write(struct.pack('<HH', i, bones.find(bones[i].parent.name)))

    MatrixOffset = f.tell()
    for i in range(len(bones)):
        bonemat = bones[i].matrix_local
        quat = bones[i].matrix.to_3x3().to_quaternion()

        if bones[i].parent:
            parent_invert = bones[i].parent.matrix_local.inverted()
            relative_mat = parent_invert @ bonemat
            #trans = bonemat.to_translation() - bones[i].parent.matrix_local.to_translation() if bones[i].parent else bonemat.to_translation()
            trans = relative_mat.to_translation()
        else:
            trans = bonemat.to_translation()

        scale = bonemat.to_scale()
        f.write(struct.pack('<ffff', quat[1], quat[2], quat[3], quat[0]))
        f.write(struct.pack('<ffff', trans.x, trans.y, trans.z, 1.0))
        f.write(struct.pack('<ffff', scale.x, scale.y, scale.z, 1.0))

    ParentPairIndexOffset = f.tell()
    for i in range(len(bones)):
        f.write(struct.pack('<H', i))

    UnkSection4Offset = f.tell()
    while (f.tell() % 16 != 0):
        f.write(struct.pack('<B', 0))

    BoneStringTableOffset = f.tell()
    #precalculate strings
    bonenames = []
    for bone in bones:
        name = bone.name.encode('utf-8') + b'\x00'
        bonenames.append(name)
    f.write(struct.pack('<IIIIII', 2, 12, 16, 20, 2695287, 2093464804)) #always the same
    f.write(struct.pack('<IIII', 0, 8, 8, 0)) #always size, 8, 8, size + 4

    encodedstringbuffersize = 0
    SizeStart = f.tell()
    for i in range(len(bonenames)):
        # pointer calculated from number of pointers ahead + already encoded strings
        f.write(struct.pack('<I', (len(bonenames)-i)*4 + encodedstringbuffersize))
        encodedstringbuffersize = encodedstringbuffersize + len(bonenames[i])
    for i in range(len(bonenames)):
        f.write(struct.pack(f'{len(bonenames[i])}s', bonenames[i]))
    while (f.tell() % 4 != 0):
        f.write(struct.pack('<B', 0))
    Size = f.tell() - SizeStart
    f.write(struct.pack('<I', 0)) #Unknown Value, maybe another hash, pray 0 works
    f.write(struct.pack('<I', 0)) #at least 4 bytes before padding
    while (f.tell() % 16 != 0):
        f.write(struct.pack('<B', 0))
    BoneStringTableSize = f.tell() - BoneStringTableOffset
    pos = f.tell()
    f.seek(BoneStringTableOffset + 24)
    f.write(struct.pack('<IIII', Size, 8, 8, Size+4)) #always size, 8, 8, size + 4
    f.seek(pos)

    bonehashesoffset = f.tell()
    for i in range(len(bones)):
        f.write(struct.pack('<I', crc32_bzip2(bones[i].name.encode('utf-8'))))

    UnkSection2Offset = f.tell()
    UnkSection3Offset = f.tell()
    while (f.tell() % 16 != 0):
        f.write(struct.pack('<B', 0))
    BoneHashSize = f.tell() - bonehashesoffset

    totalSize = f.tell() - sectionStart
    f.seek(sectionStart + 4)
    f.write(struct.pack('<I', totalSize))
    f.write(struct.pack('<I', BoneStringTableSize))
    f.write(struct.pack('<I', BoneHashSize))
    f.seek(sectionStart + 24)
    f.write(struct.pack('<I', MatrixOffset - f.tell()))
    f.write(struct.pack('<I', ParentPairIndexOffset - f.tell()))
    f.write(struct.pack('<I', bonehashesoffset - f.tell()))
    f.write(struct.pack('<I', UnkSection2Offset - f.tell()))
    f.write(struct.pack('<I', UnkSection3Offset - f.tell()))
    f.write(struct.pack('<I', UnkSection4Offset - f.tell()))
    f.write(struct.pack('<I', BoneStringTableOffset - f.tell()))
    return totalSize
