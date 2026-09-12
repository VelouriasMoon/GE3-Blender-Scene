import os
import bpy
from bpy.types import Context, Panel, PropertyGroup, Operator, UIList

# A lot of the data for GE3 models isn't standard to blender and i don't know enough to just make it from nothing.
# So when a model is import we'll store all that extra data so it can be utilized for exporting. Data will also be
# exposed in panels so that it can be edited if need be.

class GE3MDL_Mat_TRPS(PropertyGroup):
    CullBackfaces : bpy.props.BoolProperty(default=True) # type: ignore
    Prop0x10 : bpy.props.IntProperty(default=0) # type: ignore
    UseAlpha : bpy.props.BoolProperty(default=False) # type: ignore
    Prop0x18 : bpy.props.IntProperty(default=0) # type: ignore
    Prop0x1C : bpy.props.IntProperty(default=0) # type: ignore
    Prop0x20 : bpy.props.IntProperty(default=0) # type: ignore
    Prop0x24 : bpy.props.IntProperty(default=0) # type: ignore

class GE3MDL_Mat_CSTV(PropertyGroup):
    ParameterName : bpy.props.StringProperty() # type: ignore

class GE3MDL_Mat_CSTS(PropertyGroup):
    Parameters : bpy.props.CollectionProperty(type=GE3MDL_Mat_CSTV) # type: ignore
    Active_Index : bpy.props.IntProperty(name="List Index", description="Blender Only Propery", default=0) # type: ignore

class GE3MDL_Mat_EFFE(PropertyGroup):
    ShaderName : bpy.props.StringProperty() # type: ignore

class GE3MDL_Mat_SSTV(PropertyGroup):
    SamplerName : bpy.props.StringProperty() # type: ignore
    TexturePath : bpy.props.StringProperty(subtype='FILE_PATH') # type: ignore
    
class GE3MDL_Mat_SAMP(PropertyGroup):
    Samplers : bpy.props.CollectionProperty(type=GE3MDL_Mat_SSTV) # type: ignore
    Active_Index : bpy.props.IntProperty(name="List Index", description="Blender Only Propery", default=0) # type: ignore

class GE3MDL_Shader_XXSHElement(PropertyGroup):
    ParameterName : bpy.props.StringProperty() # type: ignore
    ParameterOffset : bpy.props.IntProperty() # type: ignore
    ParameterType : bpy.props.EnumProperty(name="Shader Var Type", description="_D3D_SHADER_VARIABLE_TYPE",
        items = [
            ('D3D_SVT_VOID',                        'Void',                     '', 0),
            ('D3D_SVT_BOOL',                        'Bool',                     '', 1),
            ('D3D_SVT_INT',                         'Int',                      '', 2),
            ('D3D_SVT_FLOAT',                       'Float',                    '', 3),
            ('D3D_SVT_STRING',                      'String',                   '', 4),
            ('D3D_SVT_TEXTURE',                     'Texture',                  '', 5),
            ('D3D_SVT_TEXTURE1D',                   'Texture1D',                '', 6),
            ('D3D_SVT_TEXTURE2D',                   'Texture2D',                '', 7),
            ('D3D_SVT_TEXTURE3D',                   'Texture3D',                '', 8),
            ('D3D_SVT_TEXTURECUBE',                 'TextureCude',              '', 9),
            ('D3D_SVT_SAMPLER',                     'Sampler',                  '', 10),
            ('D3D_SVT_SAMPLER1D',                   'Sampler1D',                '', 11),
            ('D3D_SVT_SAMPLER2D',                   'Sampler2D',                '', 12),
            ('D3D_SVT_SAMPLER3D',                   'Sampler3D',                '', 13),
            ('D3D_SVT_SAMPLERCUBE',                 'SamplerCude',              '', 14),
            ('D3D_SVT_PIXELSHADER',                 'PixelShader',              '', 15),
            ('D3D_SVT_VERTEXSHADER',                'VertexShader',             '', 16),
            ('D3D_SVT_PIXELFRAGMENT',               'PixelFragment',            '', 17),
            ('D3D_SVT_VERTEXFRAGMENT',              'VertexFragment',           '', 18),
            ('D3D_SVT_UINT',                        'UInt',                     '', 19),
            ('D3D_SVT_UINT8',                       'UInt8',                    '', 20),
            ('D3D_SVT_GEOMETRYSHADER',              'GeometryShader',           '', 21),
            ('D3D_SVT_RASTERIZER',                  'Rasterizer',               '', 22),
            ('D3D_SVT_DEPTHSTENCIL',                'DepthStencil',             '', 23),
            ('D3D_SVT_BLEND',                       'Blend',                    '', 24),
            ('D3D_SVT_BUFFER',                      'Buffer',                   '', 25),
            ('D3D_SVT_CBUFFER',                     'CBuffer',                  '', 26),
            ('D3D_SVT_TBUFFER',                     'TBuffer',                  '', 27),
            ('D3D_SVT_TEXTURE1DARRAY',              'Texture1DArray',           '', 28),
            ('D3D_SVT_TEXTURE2DARRAY',              'Texture2DArray',           '', 29),
            ('D3D_SVT_RENDERTARGETVIEW',            'RenderTargetView',         '', 30),
            ('D3D_SVT_DEPTHSTENCILVIEW',            'DepthStencilView',         '', 31),
            ('D3D_SVT_TEXTURE2DMS',                 'Texture2DMs',              '', 32),
            ('D3D_SVT_TEXTURE2DMSARRAY',            'Texture2DMsArray',         '', 33),
            ('D3D_SVT_TEXTURECUBEARRAY',            'TextureCubeArray',         '', 34),
            ('D3D_SVT_HULLSHADER',                  'HullShader',               '', 35),
            ('D3D_SVT_DOMAINSHADER',                'DomainShader',             '', 36),
            ('D3D_SVT_INTERFACE_POINTER',           'InterfacePointer',         '', 37),
            ('D3D_SVT_COMPUTESHADER',               'ComputeShader',            '', 38),
            ('D3D_SVT_DOUBLE',                      'Double',                   '', 39),
            ('D3D_SVT_RWTEXTURE1D',                 'RWTexture1D',              '', 40),
            ('D3D_SVT_RWTEXTURE1DARRAY',            'RWTexture1DArray',         '', 41),
            ('D3D_SVT_RWTEXTURE2D',                 'RWTexture2D',              '', 42),
            ('D3D_SVT_RWTEXTURE2DARRAY',            'RWTexture2DArray',         '', 43),
            ('D3D_SVT_RWTEXTURE3D',                 'RWTexture3D',              '', 44),
            ('D3D_SVT_RWBUFFER',                    'RWBuffer',                 '', 45),
            ('D3D_SVT_BYTEADDRESS_BUFFER',          'ByteAddressBuffer',        '', 46),
            ('D3D_SVT_RWBYTEADDRESS_BUFFER',        'RWByteAddressBuffer',      '', 47),
            ('D3D_SVT_STRUCTURED_BUFFER',           'Structured',               '', 48),
            ('D3D_SVT_RWSTRUCTURED_BUFFER',         'RWStructured',             '', 49),
            ('D3D_SVT_APPEND_STRUCTURED_BUFFER',    'AppendStructureBuffer',    '', 50),
            ('D3D_SVT_CONSUME_STRUCTURED_BUFFER',   'ConsumeStructureBuffer',   '', 51),
            ('D3D_SVT_MIN8FLOAT',                   'Min8Float',                '', 52),
            ('D3D_SVT_MIN10FLOAT',                  'Min10Float',               '', 53),
            ('D3D_SVT_MIN16FLOAT',                  'Min16Float',               '', 54),
            ('D3D_SVT_MIN12INT',                    'Min12Int',                 '', 55),
            ('D3D_SVT_MIN16INT',                    'Min16Int',                 '', 56),
            ('D3D_SVT_MIN16UINT',                   'Min16UInt',                '', 57)
        ]
    ) # type: ignore
    ParameterSize : bpy.props.IntProperty(default=0) # type: ignore

class GE3MDL_Shader_XXSH(PropertyGroup):
    Parameters : bpy.props.CollectionProperty(type=GE3MDL_Shader_XXSHElement) # type: ignore
    Active_Index : bpy.props.IntProperty(name="List Index", description="Blender Only Propery", default=0) # type: ignore

class GE3MDL_Shader_SHBIElement(PropertyGroup):
    ParameterName : bpy.props.StringProperty() # type: ignore
    ParameterOffset : bpy.props.IntProperty() # type: ignore
    ParameterSize : bpy.props.IntProperty(default=0) # type: ignore

class GE3MDL_Shader_SHBI(PropertyGroup):
    Parameters : bpy.props.CollectionProperty(type=GE3MDL_Shader_SHBIElement) # type: ignore
    Active_Index : bpy.props.IntProperty(name="List Index", description="Blender Only Propery", default=0) # type: ignore

class GE3MDL_Shader_XXSB(PropertyGroup):
    has_shbi_1 : bpy.props.BoolProperty(default=False) # type: ignore
    has_shbi_2 : bpy.props.BoolProperty(default=False) # type: ignore
    XXSH : bpy.props.PointerProperty(type=GE3MDL_Shader_XXSH) # type: ignore
    SHBI1 : bpy.props.PointerProperty(type=GE3MDL_Shader_SHBI) # type: ignore
    SHBI2 : bpy.props.PointerProperty(type=GE3MDL_Shader_SHBI) # type: ignore

class GE3MDL_Shader_SHCO(PropertyGroup):
    Name : bpy.props.StringProperty() # type: ignore
    SHCORawData : bpy.props.StringProperty() # type: ignore

class GE3MDL_Shader_SMST(PropertyGroup):
    Name : bpy.props.StringProperty() # type: ignore
    SMSTRawData : bpy.props.StringProperty() # type: ignore

class GE3MDL_Shader_Constants(PropertyGroup):
    SHCOs : bpy.props.CollectionProperty(type=GE3MDL_Shader_SHCO)# type: ignore
    active_shco_index : bpy.props.IntProperty(name="List Index", description="Blender Only Propery", default=0) # type: ignore
    SMSTs : bpy.props.CollectionProperty(type=GE3MDL_Shader_SMST)# type: ignore
    active_smst_index : bpy.props.IntProperty(name="List Index", description="Blender Only Propery", default=0) # type: ignore    

class GE3MDL_Material(PropertyGroup):
    dataImported : bpy.props.BoolProperty(default=False) # type: ignore
    has_VX_CSTS : bpy.props.BoolProperty(default=False) # type: ignore
    has_VX_SAMP : bpy.props.BoolProperty(default=False) # type: ignore
    has_PX_CSTS : bpy.props.BoolProperty(default=False) # type: ignore
    has_PX_SAMP : bpy.props.BoolProperty(default=False) # type: ignore

    EFFE : bpy.props.PointerProperty(type=GE3MDL_Mat_EFFE) # type: ignore
    TRSP : bpy.props.PointerProperty(type=GE3MDL_Mat_TRPS) # type: ignore
    VX_CSTS : bpy.props.PointerProperty(type=GE3MDL_Mat_CSTS) # type: ignore
    VX_SAMP : bpy.props.PointerProperty(type=GE3MDL_Mat_SAMP) # type: ignore
    PX_CSTS : bpy.props.PointerProperty(type=GE3MDL_Mat_CSTS) # type: ignore
    PX_SAMP : bpy.props.PointerProperty(type=GE3MDL_Mat_SAMP) # type: ignore
    VXSB : bpy.props.PointerProperty(type=GE3MDL_Shader_XXSB) # type: ignore
    PXSB : bpy.props.PointerProperty(type=GE3MDL_Shader_XXSB) # type: ignore
    Constants : bpy.props.PointerProperty(type=GE3MDL_Shader_Constants) # type: ignore

    showTRSP : bpy.props.BoolProperty(default=False) # type: ignore
    showVXCSTS : bpy.props.BoolProperty(default=False) # type: ignore
    showPXCSTS : bpy.props.BoolProperty(default=False) # type: ignore
    showVXSAMP : bpy.props.BoolProperty(default=False) # type: ignore
    showPXSAMP : bpy.props.BoolProperty(default=False) # type: ignore
    showVXSB : bpy.props.BoolProperty(default=False) # type: ignore
    showPXSB : bpy.props.BoolProperty(default=False) # type: ignore
    showVertex : bpy.props.BoolProperty(default=False) # type: ignore
    showPixel : bpy.props.BoolProperty(default=False) # type: ignore