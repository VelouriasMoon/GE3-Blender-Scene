import struct, os, json, enum
import mathutils, math
from typing import Set
import bpy
from bpy_extras.io_utils import ImportHelper
from bpy.types import Context, Operator
from bpy.props import StringProperty, BoolProperty, FloatProperty, EnumProperty

ShaderInfoLoad = False
ShaderInfoJson = "ShaderInfo.json"
ShaderInfo = {}

################################################################
#########               Helper Functions             ###########
################################################################

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

def to_signed(bb):
    return bb - 256 if bb > 127 else bb

def read_null_terminated_string(file_object, encoding='utf-8'):
    byte_array = bytearray()
    while True:
        char = file_object.read(1)
        # End of file or null terminator reached
        if not char or char == b'\x00':
            break
        byte_array.extend(char)
    return byte_array.decode(encoding)

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

################################################################
#########                  Importers                 ###########
################################################################

class ImportMDL(Operator, ImportHelper):
    bl_idname = "ge3mdl.importmdl"
    bl_label = "Import .mdl"
    bl_description = "Import a MDL model from God Eater 3"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: StringProperty( default='*.mdl', options={'HIDDEN'} ) # type: ignore
    import_scale: FloatProperty(name="Scale", default=1.0) # type: ignore
    bone_length: FloatProperty(name="Bone Length", default=0.1) # type: ignore
    import_normals: BoolProperty(name="Import Normals", default=True) # type: ignore
    import_morphs: BoolProperty(name="Import Morphs", default=True) # type: ignore
    import_bitan: EnumProperty(
        name="Import Binormals and Tangents",
        items=(
            ("None", "None", "Do not import binormals and tangents"),
            ("As Vertex Colors", "As Vertex Colors", "Import binormals and tangents as vertex colors"),
            ("As Custom Data", "As Custom Data", "Import binormals and tangents as custom data layers"),
        ),
        default="None"
    ) # type: ignore

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        col = box.column()
        col.label(text="General", icon='SETTINGS')
        col.prop(self, "import_scale")
        box = layout.box()
        col = box.column()
        col.label(text="Mesh", icon='MESH_DATA')
        col.prop(self, "import_normals")
        col.prop(self, "import_morphs")
        col.prop(self, "import_bitan")
        box = layout.box()
        col = box.column()
        col.label(text="Skeleton", icon='ARMATURE_DATA')
        col.prop(self, "bone_length")

    def execute(self, context):
        with open(self.filepath, 'r+b') as f:
            magic = f.read(4)
            if ( magic != b'KPKy'):
                self.report({'WARNING'}, f"Target file is not a GE3 skeleton, expected header 'KPKy' got '{magic.decode('utf-8')}'")
                return {'CANCELLED'}
            else:
                if not ShaderInfoLoad:
                    if not loadShaderInfo():
                        self.report({'ERROR'}, "Failed to load ShaderInfo.json, unable to read mdl properly")
                
                SectionCount = struct.unpack('<I', f.read(4))[0]
                f.read(4)
                SectionOffsets = []
                for _ in range(SectionCount):
                    SectionOffsets.append(struct.unpack('<I', f.read(4))[0])
                MESHSectionOffset, GPRSectionOffset, NODTSectionOffset, BRNTSectionOffset, _60SESectionOffset, MORPSectionOffset = 0, 0, 0, 0, 0, 0

                for section in SectionOffsets:
                    if section == 0:
                        continue
                    f.seek(section)
                    magic = f.read(4).decode('utf-8').rstrip("\x00")
                    f.seek(-4, 1)
                    if magic == "MESH":
                        MESHSectionOffset = section
                    elif magic == "GPR":
                        GPRSectionOffset = section
                    elif magic == "NODT":
                        NODTSectionOffset = section
                    elif magic == "BRNT":
                        BRNTSectionOffset = section
                    elif magic == "60SE":
                        _60SESectionOffset = section
                    elif magic == "MORP":
                        MORPSectionOffset = section
                    else:
                        self.report({'INFO'}, f"Section magic {magic} is not supported.")

                BoneIDMap = None
                MeshBoneCount = 0
                if BRNTSectionOffset != 0:
                    f.seek(BRNTSectionOffset)
                    BoneIDMap, MeshBoneCount = LoadBNTR(f)

                #load MESH section first for important model infomation.
                f.seek(MESHSectionOffset)
                ModelName, SceneName, Prims, MeshBones = LoadMESH(f, MeshBoneCount)

                new_collection = bpy.data.collections.new(ModelName)
                bpy.context.scene.collection.children.link(new_collection)
                SceneRoot = bpy.data.objects.new(SceneName, None)
                SceneRoot.rotation_euler = mathutils.Euler((math.radians(90),0,0))
                SceneRoot.scale = (self.import_scale, self.import_scale, self.import_scale)
                SceneRoot.empty_display_size = 0.1
                new_collection.objects.link(SceneRoot)

                #load skeleton and bone mapping for GPR section
                Armature = None
                BoneNames = None
                if _60SESectionOffset != 0:
                    f.seek(_60SESectionOffset)
                    Armature, BoneNames = Load60SE(f, SceneRoot, MeshBones, self.bone_length)

                #if model has morphs add those to the primitives
                hasMorph = False
                if MORPSectionOffset != 0:
                    f.seek(MORPSectionOffset)
                    _, _, Prims, _ = LoadMESH(f, MeshBoneCount, Prims)
                    hasMorph = True

                #Final load of GPR section, this is where the actual mesh data is stored and will be bound to the blender objects.
                f.seek(GPRSectionOffset)
                LoadGPR(self, f, Armature, new_collection, SceneRoot, BoneNames, BoneIDMap, Prims, hasMorph)
                
                return {'FINISHED'}

class ImportSKL(Operator, ImportHelper):
    bl_idname = "ge3mdl.importskl"
    bl_label = "Import .skl"
    bl_description = "Import a SKL skeleton from God Eater 3"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: StringProperty( default='*.skl', options={'HIDDEN'} ) # type: ignore
    import_scale: FloatProperty(name="Scale", default=1.0) # type: ignore
    bone_length: FloatProperty(name="Bone Length", default=0.1) # type: ignore

    def draw(self, context):
            layout = self.layout
            box = layout.box()
            col = box.column()
            col.label(text="General", icon='SETTINGS')
            col.prop(self, "import_scale")
            box = layout.box()
            col = box.column()
            col.label(text="Skeleton", icon='ARMATURE_DATA')
            col.prop(self, "bone_length")

    def execute(self, context):
        with open(self.filepath, 'r+b') as f:
            magic = f.read(4)
            if ( magic != b'60SE'):
                self.report({'WARNING'}, f"Target file is not a GE3 skeleton, expected header '60SE' got '{magic.decode('utf-8')}'")
                return {'CANCELLED'}
            else:
                f.seek(0)

                new_collection = bpy.data.collections.new(os.path.splitext(os.path.basename(self.filepath))[0])
                bpy.context.scene.collection.children.link(new_collection)
                SceneRoot = bpy.data.objects.new("VisualSceneNode", None)
                SceneRoot.rotation_euler = mathutils.Euler((math.radians(90),0,0))
                SceneRoot.scale = (self.import_scale, self.import_scale, self.import_scale)
                SceneRoot.empty_display_size = 0.1
                new_collection.objects.link(SceneRoot)

                Load60SE(f, SceneRoot, self.bone_length)
                return {'FINISHED'}

################################################################
#########               Read Functions               ###########
################################################################

def LoadMESH(data, MeshBoneCount, PRIMs = None):
    magic = data.read(4)
    sectionSize = struct.unpack('<I', data.read(4))[0]
    SectionEnd = data.tell() + sectionSize
    ModelName = None
    SceneName = None
    StringTable = []
    TRPSs = []
    EFFEs = []
    CSTSs = []
    SAMPs = []
    MATEs = []
    if PRIMs is None:
        PRIMs = []
    Bones = {}

    #Read MESH section into dicts, we'll use these later to bind their data to the blender objects
    while (data.tell() < SectionEnd):
        magic = data.read(4).decode('utf-8').rstrip("\x00")
        data.seek(-4, 1)
        pos = data.tell()
        if magic == "STRB":
            data.read(4)
            size = struct.unpack('<I', data.read(4))[0]
            StringCount = struct.unpack('<I', data.read(4))[0]
            data.read(4)
            size2 = struct.unpack('<I', data.read(4))[0]
            end = data.tell() + size2
            for _ in range(StringCount):
                StringTable.append(read_null_terminated_string(data))
            pos = data.tell()
            data.read(end - data.tell())
        elif magic == "DSNA":
            data.read(8)
            ModelName = StringTable[struct.unpack('<I', data.read(4))[0]]
            SceneName = StringTable[struct.unpack('<I', data.read(4))[0]]
        elif magic == "TRSP":
            TRPS = {}
            TRPS["magic"] = data.read(4).decode('utf-8').rstrip("\x00")
            data.read(4) #Skip section size
            TRPS["id"] = struct.unpack('<I', data.read(4))[0] #This is the same as the index, ids always goes in order
            TRPS["CullBackfaces"] = struct.unpack('<I', data.read(4))[0]
            TRPS["Prop0x10"] = struct.unpack('<I', data.read(4))[0]
            TRPS["UseAlpha"] = struct.unpack('<I', data.read(4))[0]
            TRPS["Prop0x18"] = struct.unpack('<I', data.read(4))[0]
            TRPS["Prop0x1C"] = struct.unpack('<I', data.read(4))[0]
            TRPS["Prop0x20"] = struct.unpack('<I', data.read(4))[0]
            TRPS["Prop0x24"] = struct.unpack('<I', data.read(4))[0]
            TRPSs.append(TRPS)
        elif magic == "EFFE":
            EFFE = {}
            EFFE["magic"] = data.read(4).decode('utf-8').rstrip("\x00")
            data.read(4) #Skip section size
            EFFE["id"] = struct.unpack('<I', data.read(4))[0] #This is the same as the index, ids always goes in order
            EFFE["MaterialName"] = StringTable[struct.unpack('<I', data.read(4))[0]]
            EFFE["ShaderName"] = StringTable[struct.unpack('<I', data.read(4))[0]]
            EFFE["ShaderBindingName"] = StringTable[struct.unpack('<I', data.read(4))[0]]

            TPAS = {}
            TPAS["magic"] = data.read(4).decode('utf-8').rstrip("\x00")
            data.read(4) #Skip section size
            TPAS["Prop0x00"] = struct.unpack('<I', data.read(4))[0]
            TPAS["Prop0x04"] = struct.unpack('<I', data.read(4))[0]
            TPAS["TRPS"] = TRPSs[struct.unpack('<I', data.read(4))[0]]
            TPAS["MaterialName"] = StringTable[struct.unpack('<I', data.read(4))[0]]
            TPAS["ShaderBindingName"] = StringTable[struct.unpack('<I', data.read(4))[0]]
            TPAS["Prop0x14"] = struct.unpack('<I', data.read(4))[0]

            EFFE["TPAS"] = TPAS
            EFFEs.append(EFFE)
        elif magic == "CSTS":
            CSTS = {}
            CSTS["magic"] = data.read(4).decode('utf-8').rstrip("\x00")
            Size = struct.unpack('<I', data.read(4))[0]
            CSTS["id"] = struct.unpack('<I', data.read(4))[0] #This is the same as the index, ids always goes in order
            CSTS["CSTVs"] = []
            for _ in range(int((Size - 4) / 16)):
                CSTV = {}
                CSTV["magic"] = data.read(4).decode('utf-8').rstrip("\x00")
                data.read(4) #Skip section size
                CSTV["ParameterName"] = StringTable[struct.unpack('<I', data.read(4))[0]]
                CSTV["SHCOBindingName"] = StringTable[struct.unpack('<I', data.read(4))[0]]
                CSTS["CSTVs"].append(CSTV)
            CSTSs.append(CSTS)
        elif magic == "SAMP":
            SAMP = {}
            SAMP["magic"] = data.read(4).decode('utf-8').rstrip("\x00")
            Size = struct.unpack('<I', data.read(4))[0]
            SAMP["id"] = struct.unpack('<I', data.read(4))[0] #This is the same as the index, ids always goes in order
            SAMP["TextureSamples"] = []
            for _ in range(int((Size - 4) / 20)):
                TextureSample = {}
                TextureSample["magic"] = data.read(4).decode('utf-8').rstrip("\x00")
                data.read(4) #Skip section size
                TextureSample["SamplerName"] = StringTable[struct.unpack('<I', data.read(4))[0]]
                TextureSample["TexturePath"] = StringTable[struct.unpack('<I', data.read(4))[0]]
                TextureSample["SMSTBindingName"] = StringTable[struct.unpack('<I', data.read(4))[0]]
                SAMP["TextureSamples"].append(TextureSample)
            SAMPs.append(SAMP)
        elif magic == "MATE":
            MATE = {}
            MATE["magic"] = data.read(4).decode('utf-8').rstrip("\x00")
            data.read(4) #Skip section size
            MATE["id"] = struct.unpack('<I', data.read(4))[0] #This is the same as the index, ids always goes in order
            MATE["MaterialName"] = StringTable[struct.unpack('<I', data.read(4))[0]]
            MATE["MaterialBindingName"] = StringTable[struct.unpack('<I', data.read(4))[0]]
            MATE["EFFE"] = EFFEs[struct.unpack('<I', data.read(4))[0]]
            VX_CSTS_ID = struct.unpack('<i', data.read(4))[0]
            MATE["VX_CSTS"] = CSTSs[VX_CSTS_ID] if VX_CSTS_ID != -1 else None
            VX_SAMP_ID = struct.unpack('<i', data.read(4))[0]
            MATE["VX_SAMP"] = SAMPs[VX_SAMP_ID] if VX_SAMP_ID != -1 else None
            PX_CSTS_ID = struct.unpack('<i', data.read(4))[0]
            MATE["PX_CSTS"] = CSTSs[PX_CSTS_ID] if PX_CSTS_ID != -1 else None
            PX_SAMP_ID = struct.unpack('<i', data.read(4))[0]
            MATE["PX_SAMP"] = SAMPs[PX_SAMP_ID] if PX_SAMP_ID != -1 else None
            MATEs.append(MATE)
        elif magic == "VARI":
            data.read(4)
            size = struct.unpack('<I', data.read(4))[0]
            end = data.tell() + size
            data.read(4)
            name = StringTable[struct.unpack('<I', data.read(4))[0]]
            data.read(8)
            PrimCount = ( end - data.tell() ) / 36
            for i in range(int(PrimCount)):
                PRIM = {}
                PRIM["magic"] = data.read(4).decode('utf-8').rstrip("\x00")
                data.read(4) #Skip section size
                PRIM["SAMP"] = SAMPs[struct.unpack('<I', data.read(4))[0]]
                PRIM["MeshName"] = StringTable[struct.unpack('<I', data.read(4))[0]]
                PRIM["MaterialBindingName"]  = StringTable[struct.unpack('<I', data.read(4))[0]]
                PRIM["Prop0x14"] = struct.unpack('<I', data.read(4))[0]
                PRIM["MeshBindingName"]  = StringTable[struct.unpack('<I', data.read(4))[0]]
                PRIM["MATE"] = MATEs[struct.unpack('<I', data.read(4))[0]]
                PRIM["MorphTargetHash"] = struct.unpack('<I', data.read(4))[0]
                PRIMs.append(PRIM)
        elif magic == "BONE":
            data.read(4)
            size = struct.unpack('<I', data.read(4))[0]
            end = data.tell() + size
            data.read(4) #i know this is important but i don't know how
            boneNames = []
            for i in range(MeshBoneCount):
                BOIF = {}
                BOIF["magic"] = data.read(4).decode('utf-8').rstrip("\x00")
                data.read(4) #Skip section size
                BOIF["BoneName"] = StringTable[struct.unpack('<I', data.read(4))[0]]
                BOIF["IDName"] = struct.unpack('<I', data.read(4))[0]
                Bones[BOIF["BoneName"]] = BOIF
                boneNames.append(BOIF["BoneName"])
            for i in range(MeshBoneCount):
                data.read(8)
                mat = mathutils.Matrix(((struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0]),
                    (struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0]),
                    (struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0]),
                    (0.0, 0.0, 0.0, 1.0)))
                Bones[boneNames[i]]["Matrix"] = mat
                
        else:
            data.read(4)
            size = struct.unpack('<I', data.read(4))[0]
            data.read(size)

    return ModelName, SceneName, PRIMs, Bones

def Load60SE(data, scene_root, mesh_bones, bone_length = 0.1):
    magic = data.read(4)
    sectionSize = struct.unpack('<I', data.read(4))[0]
    StringTableSize = struct.unpack('<I', data.read(4))[0]
    HashesSize = struct.unpack('<I', data.read(4))[0]
    BoneCount = struct.unpack('<I', data.read(4))[0]
    data.read(4)

    MatrixOffset = data.tell() + struct.unpack('<I', data.read(4))[0]
    ParentIDsOffset = data.tell() + struct.unpack('<I', data.read(4))[0]
    HashesOffset = data.tell() + struct.unpack('<I', data.read(4))[0]
    data.read(12)
    StringTableOffset = data.tell() + struct.unpack('<I', data.read(4))[0]
    data.read(8)

    #Read Pairs from bone's Parent and Child ID
    ParentPairsCount = struct.unpack('<I', data.read(4))[0]
    ParentPairs = []
    for i in range(ParentPairsCount):
        child = struct.unpack('<H', data.read(2))[0]
        parent = struct.unpack('<H', data.read(2))[0]
        ParentPairs.append((child, parent))

    #Read bone matrices
    data.seek(MatrixOffset)
    matrices = []
    transforms = []
    for i in range(BoneCount):
        qx, qy, qz, qw = struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0]
        quat = mathutils.Quaternion((qw, qx, qy, qz))
        euler = quat.to_euler()
        loc = mathutils.Vector((struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0],))
        data.read(4) #Throw away the W value
        scale = mathutils.Vector((struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0], struct.unpack('<f', data.read(4))[0],))
        data.read(4) #Throw away the W value

        matrix = mathutils.Matrix.LocRotScale(loc, quat, scale)
        matrices.append(matrix)
        transforms.append((loc, quat, scale))

    #Read parent indices
    data.seek(ParentIDsOffset)
    ParentIDs = []
    for i in range(BoneCount):
        ParentIDs.append(struct.unpack('<H', data.read(2))[0])

    #Read Bone names
    data.seek(StringTableOffset)
    data.read(40)
    BoneNames = []
    TableStart = data.tell()
    for i in range(BoneCount):
        data.seek(TableStart + (4 * i))
        data.seek(data.tell() + struct.unpack('<I', data.read(4))[0])
        BoneNames.append(read_null_terminated_string(data))

    #Construct Skeleton
    new_armature = bpy.data.armatures.new(BoneNames[0])
    bone_struct = bpy.data.objects.new(BoneNames[0], new_armature)
    bone_struct.parent = scene_root
    scene_root.users_collection[0].objects.link(bone_struct)

    bpy.context.view_layer.objects.active = bone_struct
    bpy.ops.object.editmode_toggle()

    bone_array = {}
    for i in range(BoneCount):
        new_bone = new_armature.edit_bones.new(BoneNames[i])
        new_bone.use_connect = False
        new_bone.use_inherit_rotation = True
        new_bone.use_local_location = True
        new_bone.inherit_scale = 'FULL'

        new_bone.head = (0,0,0)
        new_bone.length = bone_length
        new_bone.matrix = matrices[i]
        if (ParentPairs[ParentIDs[i]][1] != 32767):
            new_bone.parent = bone_array[BoneNames[ParentPairs[ParentIDs[i]][1]]]
            new_bone.matrix = bone_array[BoneNames[ParentPairs[ParentIDs[i]][1]]].matrix @ matrices[i]
        bone_array[BoneNames[i]] = new_bone

    bpy.ops.object.editmode_toggle()
    bpy.ops.object.select_all(action='DESELECT')
    return bone_struct, BoneNames

def LoadBNTR(data):
    magic = data.read(16)
    BoneCount = struct.unpack('<I', data.read(4))[0]        #Total bones in skeleton
    MeshBoneCount = struct.unpack('<I', data.read(4))[0]    #Bones that are weighted, index used in vertex buffer
    data.read(8)
    BoneIDMap = {}
    for _ in range(BoneCount):
        BoneHash = data.read(4)
        BoneName = data.read(16).decode('utf-8')
        ID = struct.unpack('<H', data.read(2))[0]
        ParentID = struct.unpack('<H', data.read(2))[0]
        data.read(2)
        MeshID = struct.unpack('<H', data.read(2))[0]
        data.read(8)
        data.read(40) #Transform Section
        data.read(12)
        if MeshID != 65535:
            BoneIDMap[MeshID] = ID
    return BoneIDMap, MeshBoneCount

def GetDescriptorFromOffset(Descriptors, offset, buffer2 = False):
    for Descriptor in Descriptors:
        if buffer2:
            if Descriptor["faroffset"] == offset:
                return Descriptor
        else:
            if Descriptor["offset"] == offset:
                return Descriptor
    return None

def GetDescriptorFromBindingName(Descriptors, Name, Magic):
    for Descriptor in Descriptors:
        if Descriptor["magic"] == Magic:
            if Descriptor["name"] == Name:
                return Descriptor
    return None

def GetAllBoundDescriptors(Descriptors, BindingName):
    OutDes = []
    for Descriptor in Descriptors:
        if Descriptor["name"] == BindingName:
            OutDes.append(Descriptor)
    return OutDes

def GetAllDescriptorsWithMagic(Descriptors, Magic):
    OutDes = []
    for Descriptor in Descriptors:
        if Descriptor["magic"] == Magic:
            OutDes.append(Descriptor)
    return OutDes

def LoadGPR(self, data, armature, collection, scene_root, bonenamemap, boneidmap, prims, hasmorph):
    magic = data.read(4)
    data.read(4)

    platform = data.read(4).decode('utf-8').rstrip("\x00")  #Platform string, DX11 for PC and NX for Switch
    if platform != "DX11" and platform != "NX":
        self.report({'WARNING'}, f"Target file is not a DX11 GPR, expected 'DX11' or 'NX' got '{platform}'")
        return
    data.read(4)    #Unknown Size, not needed for final model load
    Buffer2OffsetStart = data.tell()

    data.read(12)   #Unknown Values, always 0x01 10 08 20 30 00 00 00 30 00 00 00
    Buffer1RelEnd = struct.unpack('<I', data.read(4))[0]
    data.read(8)
    Buffer2Offset = struct.unpack('<I', data.read(4))[0] + Buffer2OffsetStart   
    Buffer2Size = struct.unpack('<I', data.read(4))[0]
    data.read(16)
    Buffer1End = data.tell() + Buffer1RelEnd

    magic = data.read(4)
    data.read(4)
    GPRDesSize = struct.unpack('<I', data.read(4))[0]
    HeapDataSize = struct.unpack('<I', data.read(4))[0]
    HeapTotalSize = struct.unpack('<I', data.read(4))[0]
    HeapEnd = data.tell() + HeapTotalSize - 20
    StringTableSize = struct.unpack('<I', data.read(4))[0]
    data.read(4)

    GPRDesCount = struct.unpack('<I', data.read(4))[0]
    DescriptorPos = data.tell()
    data.seek(DescriptorPos + (GPRDesSize * GPRDesCount))

    StringTableStart = data.tell()
    StringTableEnd = StringTableStart + StringTableSize
    StringTable = {}
    while (data.tell() < StringTableEnd):
        StringStart = data.tell()
        StringTable[StringStart - StringTableStart] = read_null_terminated_string(data)
    ModelName = read_null_terminated_string(data)
    data.read(HeapEnd - data.tell())
    AfterStringTablePos = data.tell()

    data.seek(DescriptorPos)
    Descriptors = []
    for i in range(GPRDesCount):
        Descriptor = {}
        Descriptor["magic"] = data.read(4).decode('utf-8').rstrip("\x00")
        Descriptor["name"] = StringTable[struct.unpack('<I', data.read(4))[0]]
        data.read(4)
        Descriptor["offset"] = struct.unpack('<I', data.read(4))[0]
        Descriptor["size"] = struct.unpack('<I', data.read(4))[0]
        Descriptor["faroffset"] = struct.unpack('<I', data.read(4))[0]
        Descriptor["farsize"] = struct.unpack('<I', data.read(4))[0]
        data.read(4)
        Descriptors.append(Descriptor)
    data.seek(AfterStringTablePos)

    Buffer1Start = data.tell()
    index = 0
    for des in Descriptors:
        data.seek(Buffer1Start + des["offset"])
        if des["magic"] == "VXBO":  #Huge blob of flaots, might be the bounding box
            VXBO = []
            for i in range(des["size"] // 4):
                VXBO.append(struct.unpack('<f', data.read(4))[0])
        elif des["magic"] == "VXAR":    #Vertex Attribute Register, describes the vertex buffer layout
            VXAR = {}
            elementCount = struct.unpack('<I', data.read(4))[0]
            VXAR["Elements"] = []
            for i in range(elementCount):
                VXARElement = {}
                VXARElement['ShaderIndex'] = i
                VXARElement['offset'] = struct.unpack('<I', data.read(4))[0]
                data.read(4)
                VXARElement['size'] = struct.unpack('<I', data.read(4))[0]
                VXARElement['Format'] = struct.unpack('<I', data.read(4))[0]
                if platform == "NX":
                    VXARElement['Definition'] = struct.unpack('<I', data.read(4))[0]
                else:
                    VXARElement['Definition'] = 65535
                VXAR["Elements"].append(VXARElement)
            des["data"] = VXAR
        elif des["magic"] == "IXBF":    #Index Buffer, empty data other than a 0x57 at 0x8, the actual index data is in the far offset
            des["rawdata"] = data.read(des['size'])
        elif des["magic"] == "VXBF":    #Vertex Buffer, This one only holds the count and stride, the actual vertex data is in the far offset
            VXBF = {}
            data.read(8)
            VXBF["VertexCount"] = struct.unpack('<I', data.read(4))[0]
            VXBF["VertexStride"] = struct.unpack('<I', data.read(4))[0]
            des["data"] = VXBF
        elif des["magic"] == "VXST":    #Vertex Stream, this is the main descriptor that links the other descriptors together, it has the offsets to the vertex buffer, index buffer, and vertex attribute register
            VXST = {}
            data.read(12)
            VXST['VXBOOffset'] = struct.unpack('<I', data.read(4))[0]
            VXST['Prop0x10'] = struct.unpack('<I', data.read(4))[0]
            VXST['IXBFCount'] = struct.unpack('<I', data.read(4))[0]
            VXST['IXBFOffset']= struct.unpack('<I', data.read(4))[0]
            VXST['Slots'] = struct.unpack('<I', data.read(4))[0]
            VXST['Prop0x20'] = struct.unpack('<I', data.read(4))[0]
            VXST['Prop0x24'] = struct.unpack('<I', data.read(4))[0]
            VXST['Prop0x28'] = struct.unpack('<I', data.read(4))[0]
            VXST['Prop0x2C'] = struct.unpack('<I', data.read(4))[0]
            VXST['Prop0x30'] = struct.unpack('<f', data.read(4))[0]
            VXST['Prop0x34'] = struct.unpack('<f', data.read(4))[0]
            VXST['Prop0x38'] = struct.unpack('<f', data.read(4))[0]
            VXST['Prop0x3C'] = struct.unpack('<f', data.read(4))[0]
            VXST['Prop0x40'] = struct.unpack('<I', data.read(4))[0]
            VXST['Prop0x44'] = struct.unpack('<I', data.read(4))[0]
            VXST['VXAROffset'] = struct.unpack('<I', data.read(4))[0]
            VXST['VXBFOffset'] = struct.unpack('<I', data.read(4))[0]
            des["data"] = VXST
        elif des["magic"] == "SHMI":    #Not sure what this is for but it has a pointer to an empty string in the string table and 2 -1's
            des["rawdata"] = data.read(des['size'])
        elif des["magic"] == "VXSH" or des["magic"] == "PXSH":  #VXSH and PXSH are both formatted the same, they hold the shader's variables used or unused    
            XXSH = {}
            data.read(24)   #0x0s
            elementCount = struct.unpack('<I', data.read(4))[0]
            data.read(4)    #0x0
            XXSH["Elements"] = []
            for i in range(elementCount):
                XXSHElement = {}
                XXSHElement["ParameterName"] = StringTable[struct.unpack('<I', data.read(4))[0]]
                XXSHElement["Offset"] = struct.unpack('<I', data.read(4))[0]
                XXSHElement["Type"] = struct.unpack('<I', data.read(4))[0]
                XXSHElement["DataSize"] = struct.unpack('<I', data.read(4))[0]
                XXSH["Elements"].append(XXSHElement)
            des["data"] = XXSH
        elif des["magic"] == "SHBI":
            SHBI = {}
            data.read(16) #0x0s
            elementCount = struct.unpack('<I', data.read(4))[0]
            data.read(4)    #0x0
            SHBI["Elements"] = []
            for i in range(elementCount):
                SHBIElement = {}
                SHBIElement["ParameterName"] = StringTable[struct.unpack('<I', data.read(4))[0]]
                SHBIElement["Offset"] = struct.unpack('<I', data.read(4))[0]
                SHBIElement["DataSize"] = struct.unpack('<I', data.read(4))[0]
                SHBI['Elements'].append(SHBIElement)
            data.read(data.tell() % 16) #Align to 16 bytes
            des['data'] = SHBI
        elif des["magic"] == "SHCO":    #Shader Constant value
            SHCO = {}
            SHCO["RawValues"] = data.read(32)   #Holds the Shader Constants values, these are formatted based on VXSH/PSXH
            des["data"] = SHCO
        elif des["magic"] == "SMST":    #Shader Sampler
            SMST = {}
            SMST["RawValues"] = data.read(32)  #Samplers always have the same data but let's store it anyways
            des["data"] = SMST
        elif des["magic"] == "VXSB" or des["magic"] == "PXSB":
            XXSB = {}
            data.read(8)
            XXSB["XXSH"] = struct.unpack('<I', data.read(4))[0]
            XXSB["SHBI1"] = struct.unpack('<i', data.read(4))[0]
            XXSB["SHBI2"] = struct.unpack('<i', data.read(4))[0]
            data.read(12)
            des['data'] = XXSB
        else:
            continue

    Objects = []
    MorphObjects = {}
    for i in range(len(prims)):
        new_mesh = bpy.data.meshes.new(prims[i]["MeshBindingName"])

        vertarray = []
        indexarray = []
        normarray = []
        BoneIndexArray = []
        BoneWeightArray = []
        TexcoordArrays = {}
        ColorArrays = {}
        TangentArrays = {}
        BinormalArrays = {}

        vxst = GetDescriptorFromBindingName(Descriptors, prims[i]["MeshBindingName"], "VXST")
        vxbf = GetDescriptorFromOffset(Descriptors, vxst['data']['VXBFOffset'])
        vxar = GetDescriptorFromOffset(Descriptors, vxst['data']['VXAROffset'])
        ixbf = GetDescriptorFromOffset(Descriptors, vxst['data']['IXBFOffset'])
        shaderdef = ShaderInfo[prims[i]["MATE"]["EFFE"]["ShaderName"]]

        #Process Vert buffer
        data.seek(Buffer2Offset + vxbf['faroffset'])
        for vert in range(vxbf['data']['VertexCount']):
            vertdata = data.read(vxbf['data']['VertexStride'])
            if platform == "DX11":
                for element in vxar['data']['Elements']:
                    if shaderdef[element['ShaderIndex']] == "POSITION":
                        x, y, z = struct.unpack_from('<fff', vertdata, element['offset'])
                        vertarray.append((x, y, z))
                    elif shaderdef[element['ShaderIndex']] == "NORMAL":
                        x, y, z = struct.unpack_from('<fff', vertdata, element['offset'])
                        normarray.append((x,y,z))
                    elif shaderdef[element['ShaderIndex']] == "TEXCOORD":
                        u, v = struct.unpack_from('<ee', vertdata, element['offset'])
                        if element['offset'] not in TexcoordArrays:
                            TexcoordArrays[element['offset']] = []
                        TexcoordArrays[element['offset']].append((u, v)) 
                    elif shaderdef[element['ShaderIndex']] == "BLENDWEIGHT":
                        w1, w2, w3, w4 = struct.unpack_from('<BBBB', vertdata, element['offset'])
                        BoneWeightArray.append((w1, w2, w3, w4))
                    elif shaderdef[element['ShaderIndex']] == "BLENDINDICES":
                        w1, w2, w3, w4 = struct.unpack_from('<BBBB', vertdata, element['offset'])
                        BoneIndexArray.append((w1, w2, w3, w4))
                    elif shaderdef[element['ShaderIndex']] == "COLOR":
                        r, g, b, a = struct.unpack_from('<BBBB', vertdata, element['offset'])
                        if element['offset'] not in ColorArrays:
                            ColorArrays[element['offset']] = []
                        ColorArrays[element['offset']].append((r, g, b, a))
                    elif shaderdef[element['ShaderIndex']] == "TANGENT":
                        r, g, b, a = struct.unpack_from('<BBBB', vertdata, element['offset'])
                        if element['offset'] not in TangentArrays:
                            TangentArrays[element['offset']] = []
                        TangentArrays[element['offset']].append((r, g, b, a))
                    elif shaderdef[element['ShaderIndex']] == "BINORMAL":
                        r, g, b, a = struct.unpack_from('<BBBB', vertdata, element['offset'])
                        if element['offset'] not in BinormalArrays:
                            BinormalArrays[element['offset']] = []
                        BinormalArrays[element['offset']].append((r, g, b, a))
                    else:
                        print(f"Unhandled vertex element '{shaderdef[element['ShaderIndex']]}'")
            elif platform == "NX":
                for element in vxar['data']['Elements']:
                    if element['Definition'] == 0:
                        x, y, z = struct.unpack_from('<fff', vertdata, element['offset'])
                        vertarray.append((x, y, z))
                    elif element['Definition'] == 2:
                        xb, yb, zb, _ = struct.unpack_from('<BBBB', vertdata, element['offset'])
                        x = to_signed(xb) / 127.0
                        y = to_signed(yb) / 127.0
                        z = to_signed(zb) / 127.0
                        normarray.append( (max(x, -1.0), max(y, -1.0), max(z, -1.0)) )
                    elif element['Definition'] == 8:
                        u, v = struct.unpack_from('<ee', vertdata, element['offset'])
                        if element['offset'] not in TexcoordArrays:
                            TexcoordArrays[element['offset']] = []
                        TexcoordArrays[element['offset']].append((u, v)) 
                    elif element['Definition'] == 1:
                        w1, w2, w3, w4 = struct.unpack_from('<BBBB', vertdata, element['offset'])
                        BoneWeightArray.append((w1, w2, w3, w4))
                    elif element['Definition'] == 7:
                        w1, w2, w3, w4 = struct.unpack_from('<BBBB', vertdata, element['offset'])
                        BoneIndexArray.append((w1, w2, w3, w4))
                    #elif element['Definition'] == ?:
                    #    r, g, b, a = struct.unpack_from('<BBBB', vertdata, element['offset'])
                    #    if element['offset'] not in ColorArrays:
                    #        ColorArrays[element['offset']] = []
                    #    ColorArrays[element['offset']].append((r, g, b, a))
                    elif element['Definition'] == 16:
                        r, g, b, a = struct.unpack_from('<BBBB', vertdata, element['offset'])
                        if element['offset'] not in TangentArrays:
                            TangentArrays[element['offset']] = []
                        TangentArrays[element['offset']].append((r, g, b, a))
                    elif element['Definition'] == 17:
                        r, g, b, a = struct.unpack_from('<BBBB', vertdata, element['offset'])
                        if element['offset'] not in BinormalArrays:
                            BinormalArrays[element['offset']] = []
                        BinormalArrays[element['offset']].append((r, g, b, a))
                    else:
                        print(f"Unhandled vertex element '{shaderdef[element['ShaderIndex']]}'")

        #Process Index Buffer
        data.seek(Buffer2Offset + ixbf['faroffset'])
        for _ in range(int(vxst['data']['IXBFCount']/3)):
            if vxbf['data']['VertexCount'] > 65535:
                indexarray.append(( struct.unpack('<I', data.read(4))[0], struct.unpack('<I', data.read(4))[0], struct.unpack('<I', data.read(4))[0] ))
            else:
                indexarray.append(( struct.unpack('<H', data.read(2))[0], struct.unpack('<H', data.read(2))[0], struct.unpack('<H', data.read(2))[0] ))

        new_mesh.from_pydata(vertarray, [], indexarray, False)
        new_mesh.update()
        new_obj = bpy.data.objects.new(prims[i]["MeshName"], new_mesh)
        if armature is not None:
            new_obj.parent = armature
            new_obj.modifiers.new(name='Armature', type='ARMATURE')
            new_obj.modifiers['Armature'].object = armature

        #Process Normals
        if self.import_normals:
            new_obj.data.polygons.foreach_set("use_smooth", [True] * len(new_obj.data.polygons))
            try:
                new_obj.data.normals_split_custom_set_from_vertices(normarray)
                new_obj.data.update()
            except Exception as e:
                self.report({'WARNING'}, f"Failed to set custom normals for mesh '{new_obj.name}': {e}")

        # Process Weights 
        if armature is not None:
            vg_cache = {}
            vcount = len(new_obj.data.vertices)
            for v_idx in range(vcount):
                try:
                    bone_indices = BoneIndexArray[v_idx]
                    bone_weights = BoneWeightArray[v_idx]
                except Exception:
                    continue

                for j in range(4):
                    try:
                        mesh_bone_index = bone_indices[j]
                        raw_weight = bone_weights[j]
                    except Exception:
                        continue

                    if raw_weight <= 0:
                        continue

                    # Map mesh bone index to skeleton bone id (BoneIDMap -> boneid)
                    boneid = boneidmap.get(mesh_bone_index, None) if isinstance(boneidmap, dict) else boneidmap[mesh_bone_index]
                    if boneid is None:
                        continue

                    bone_name = bonenamemap[boneid]

                    group = vg_cache.get(bone_name)
                    if group is None:
                        group = new_obj.vertex_groups.get(bone_name)
                        if group is None:
                            group = new_obj.vertex_groups.new(name=bone_name)
                        vg_cache[bone_name] = group

                    group.add([v_idx], float(raw_weight) / 255.0, 'REPLACE')

        #Process Vert Colors
        groupindex = 0
        for vcolor in ColorArrays:
            colors = ColorArrays[vcolor]
            if f"Color{groupindex}" not in new_mesh.color_attributes:
                new_mesh.color_attributes.new(f"Color{groupindex}", type='BYTE_COLOR', domain='POINT')
            new_color = new_mesh.color_attributes[f"Color{groupindex}"]
            for j, vert in enumerate(new_mesh.vertices):
                new_color.data[j].color = colors[j]
            groupindex = groupindex + 1

        #Process Tangents and Binormals
        if self.import_bitan != "None":
            if self.import_bitan == "As Vertex Colors":
                groupindex = 0
                for tangents in TangentArrays:
                    tangent = TangentArrays[tangents]
                    if f"Tangent{groupindex}" not in new_mesh.color_attributes:
                        new_mesh.color_attributes.new(f"Tangent{groupindex}", type='BYTE_COLOR', domain='CORNER')
                    new_color = new_mesh.color_attributes[f"Tangent{groupindex}"]
                    for j, vert in enumerate(new_mesh.vertices):
                        new_color.data[j].color = tangent[j]
                    groupindex = groupindex + 1

                groupindex = 0
                for binorms in BinormalArrays:
                    binorm = BinormalArrays[binorms]
                    if f"Binormal{groupindex}" not in new_mesh.color_attributes:
                        new_mesh.color_attributes.new(f"Binormal{groupindex}", type='BYTE_COLOR', domain='CORNER')
                    new_color = new_mesh.color_attributes[f"Binormal{groupindex}"]
                    for j, vert in enumerate(new_mesh.vertices):
                        new_color.data[j].color = binorm[j]
                    groupindex = groupindex + 1
            elif self.import_bitan == "As Custom Data":
                groupindex = 0
                for tangents in TangentArrays:
                    tangent = TangentArrays[tangents]
                    if f"Tangent{groupindex}" not in new_mesh.attributes:
                        new_mesh.attributes.new(f"Tangent{groupindex}", type='BYTE_COLOR', domain='CORNER')
                    new_color = new_mesh.attributes[f"Tangent{groupindex}"]
                    for j, vert in enumerate(new_mesh.vertices):
                        new_color.data[j].color = tangent[j]
                    groupindex = groupindex + 1

                groupindex = 0
                for binorms in BinormalArrays:
                    binorm = BinormalArrays[binorms]
                    if f"Binormal{groupindex}" not in new_mesh.attributes:
                        new_mesh.attributes.new(f"Binormal{groupindex}", type='BYTE_COLOR', domain='CORNER')
                    new_color = new_mesh.attributes[f"Binormal{groupindex}"]
                    for j, vert in enumerate(new_mesh.vertices):
                        new_color.data[j].color = binorm[j]
                    groupindex = groupindex + 1

        #Process UVs
        groupindex = 0
        for texcoord in TexcoordArrays:
            uvarray = TexcoordArrays[texcoord]
            uv_layers = new_obj.data.uv_layers
            uv_layer = uv_layers.new(name=f"UV{groupindex}")
            uv_layers.active = uv_layer
            for face in new_obj.data.polygons:
                for vert, loop, in zip(face.vertices, face.loop_indices):
                    uv_layer.data[loop].uv = uvarray[vert]
            groupindex = groupindex + 1
        new_obj.data.uv_layers.active_index = 0

        #Setup Material
        if bpy.data.materials.get(prims[i]["MATE"]["MaterialName"]) is None:
            material = bpy.data.materials.new(prims[i]["MATE"]["MaterialName"])
            material.use_nodes = True
            if hasattr(material, "ge3mdl_material"):
                material.ge3mdl_material.dataImported = True
                mate = prims[i]["MATE"]

                effe = mate["EFFE"]
                material.ge3mdl_material.EFFE.ShaderName = effe["ShaderName"]

                trps = effe["TPAS"]["TRPS"]
                material.ge3mdl_material.TRSP.CullBackfaces = trps["CullBackfaces"]
                material.ge3mdl_material.TRSP.Prop0x10 = trps["Prop0x10"]
                material.ge3mdl_material.TRSP.UseAlpha = trps["UseAlpha"]
                material.ge3mdl_material.TRSP.Prop0x18 = trps["Prop0x18"]
                material.ge3mdl_material.TRSP.Prop0x1C = trps["Prop0x1C"]
                material.ge3mdl_material.TRSP.Prop0x20 = trps["Prop0x20"]
                material.ge3mdl_material.TRSP.Prop0x24 = trps["Prop0x24"]

                VXSB = GetDescriptorFromBindingName(Descriptors, effe['ShaderBindingName'], 'VXSB')
                if VXSB is not None:
                    vxsh = GetDescriptorFromOffset(Descriptors, VXSB['data']['XXSH'])
                    for element in vxsh['data']["Elements"]:
                        new_param = material.ge3mdl_material.VXSB.XXSH.Parameters.add()
                        new_param.ParameterName = element["ParameterName"]
                        new_param.ParameterOffset = element["Offset"]
                        new_param.ParameterType = new_param.bl_rna.properties["ParameterType"].enum_items[element["Type"]].identifier
                        new_param.ParameterSize = element["DataSize"]
                    if VXSB['data']['SHBI1'] != -1:
                        shbi1 = GetDescriptorFromOffset(Descriptors, VXSB['data']['SHBI1'])
                        material.ge3mdl_material.VXSB.has_shbi_1 = True
                        for element in shbi1['data']["Elements"]:
                            new_param = material.ge3mdl_material.VXSB.SHBI1.Parameters.add()
                            new_param.ParameterName = element["ParameterName"]
                            new_param.ParameterOffset = element["Offset"]
                            new_param.ParameterSize = element["DataSize"]
                    if VXSB['data']['SHBI2'] != -1:
                        shbi2 = GetDescriptorFromOffset(Descriptors, VXSB['data']['SHBI2'])
                        material.ge3mdl_material.VXSB.has_shbi_2 = True
                        for element in shbi2['data']["Elements"]:
                            new_param = material.ge3mdl_material.VXSB.SHBI2.Parameters.add()
                            new_param.ParameterName = element["ParameterName"]
                            new_param.ParameterOffset = element["Offset"]
                            new_param.ParameterSize = element["DataSize"]

                PXSB = GetDescriptorFromBindingName(Descriptors, effe['ShaderBindingName'], 'PXSB')
                if PXSB is not None:
                    pxsh = GetDescriptorFromOffset(Descriptors, PXSB['data']['XXSH'])
                    for element in pxsh['data']["Elements"]:
                        new_param = material.ge3mdl_material.PXSB.XXSH.Parameters.add()
                        new_param.ParameterName = element["ParameterName"]
                        new_param.ParameterOffset = element["Offset"]
                        new_param.ParameterType = new_param.bl_rna.properties["ParameterType"].enum_items[element["Type"]].identifier
                        new_param.ParameterSize = element["DataSize"]
                    if PXSB['data']['SHBI1'] != -1:
                        shbi1 = GetDescriptorFromOffset(Descriptors, PXSB['data']['SHBI1'])
                        material.ge3mdl_material.PXSB.has_shbi_1 = True
                        for element in shbi1['data']["Elements"]:
                            new_param = material.ge3mdl_material.PXSB.SHBI1.Parameters.add()
                            new_param.ParameterName = element["ParameterName"]
                            new_param.ParameterOffset = element["Offset"]
                            new_param.ParameterSize = element["DataSize"]
                    if PXSB['data']['SHBI2'] != -1:
                        shbi2 = GetDescriptorFromOffset(Descriptors, PXSB['data']['SHBI2'])
                        material.ge3mdl_material.PXSB.has_shbi_2 = True
                        for element in shbi2['data']["Elements"]:
                            new_param = material.ge3mdl_material.PXSB.SHBI2.Parameters.add()
                            new_param.ParameterName = element["ParameterName"]
                            new_param.ParameterOffset = element["Offset"]
                            new_param.ParameterSize = element["DataSize"]


                cstvNameList = {}

                if mate["PX_CSTS"] is not None:
                    csts = mate["PX_CSTS"]
                    material.ge3mdl_material.has_PX_CSTS = True
                    for cstv in csts["CSTVs"]:
                        new_cstv = material.ge3mdl_material.PX_CSTS.Parameters.add()
                        new_cstv.ParameterName = cstv["ParameterName"]
                        cstvNameList[cstv["SHCOBindingName"]] = cstv["ParameterName"]

                if mate["VX_CSTS"] is not None:
                    csts = mate["VX_CSTS"]
                    material.ge3mdl_material.has_VX_CSTS = True
                    for cstv in csts["CSTVs"]:
                        new_cstv = material.ge3mdl_material.VX_CSTS.Parameters.add()
                        new_cstv.ParameterName = cstv["ParameterName"]
                        cstvNameList[cstv["SHCOBindingName"]] = cstv["ParameterName"]

                for shco in GetAllDescriptorsWithMagic(Descriptors, "SHCO"):
                    if shco["name"] in cstvNameList:
                        new_shco = material.ge3mdl_material.Constants.SHCOs.add()
                        new_shco.Name = cstvNameList[shco["name"]]
                        new_shco.SHCORawData = shco["data"]["RawValues"].hex(' ')

                samplerNameList = {}

                if mate["PX_SAMP"] is not None:
                    samp = mate["PX_SAMP"]
                    material.ge3mdl_material.has_PX_SAMP = True
                    for sampler in samp["TextureSamples"]:
                        new_samp = material.ge3mdl_material.PX_SAMP.Samplers.add()
                        new_samp.SamplerName = sampler["SamplerName"]
                        new_samp.TexturePath = sampler["TexturePath"]
                        samplerNameList[sampler["SMSTBindingName"]] = sampler["SamplerName"]

                if mate["VX_SAMP"] is not None:
                    samp = mate["VX_SAMP"]
                    material.ge3mdl_material.has_VX_SAMP = True
                    for sampler in samp["TextureSamples"]:
                        new_samp = material.ge3mdl_material.VX_SAMP.Samplers.add()
                        new_samp.SamplerName = sampler["SamplerName"]
                        new_samp.TexturePath = sampler["TexturePath"]
                        samplerNameList[sampler["SMSTBindingName"]] = sampler["SamplerName"]

                for smst in GetAllDescriptorsWithMagic(Descriptors, "SMST"):
                    if smst["name"] in samplerNameList:
                        new_smst = material.ge3mdl_material.Constants.SMSTs.add()
                        new_smst.Name = samplerNameList[smst["name"]]
                        new_smst.SMSTRawData = smst["data"]["RawValues"].hex(' ')
                        
        else:
            material = bpy.data.materials[prims[i]["MATE"]["MaterialName"]]
        new_obj.data.materials.append(material)
        
        if prims[i]["MorphTargetHash"] == 4294967295:
            Objects.append(new_obj)
        else:
            MorphObjects[new_obj] = prims[i]

        new_obj.parent = scene_root
        collection.objects.link(new_obj)

    if hasmorph and self.import_morphs:
        for obj in MorphObjects:
            target = None
            #Try to find original mesh for morph based on name
            for mainObj in Objects:
                MorphHash = crc32_bzip2(mainObj.name.encode('utf-8'))
                if MorphHash == MorphObjects[obj]["MorphTargetHash"]:
                    target = mainObj
                    break

            if target is not None:
                morphname = MorphObjects[obj]["MeshBindingName"]
                if target.data.shape_keys is None:
                    target.shape_key_add(name="Basic")
                new_shape = target.shape_key_add(name=morphname, from_mix=False)
                source_verts = obj.data.vertices
                for j, vert in enumerate(new_shape.data):
                    vert.co = source_verts[j].co
                new_shape.value = 0.0
                bpy.data.meshes.remove(obj.data, do_unlink=True)
                #bpy.data.objects.remove(obj, do_unlink=True)
                self.report({'INFO'}, f"Added morph target {morphname} to {target.name}")
            else:
                self.report({'WARNING'}, f"Could not find morph target for {obj.name}")

