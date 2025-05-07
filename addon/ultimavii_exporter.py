# --------------------------------------------------------------------------------
# Ultima VII Revisited Exporter
# --------------------------------------------------------------------------------
# Version
# 0.1:
# - First Version
# 0.2:
# - Adding new name convention
# - Fixed shapetable script bug
# 0.3:
# - fixed frame implementation 
# 0.4:
# - added rotation
# - added multi-shape-export
# - added texture copy option
# --------------------------------------------------------------------------------

bl_info = {
    "name": "Ultima VII Revisited Exporter",
    "author": "Oliver Reischl <clawjelly@gmail.net>",
    "version": (0, 4),
    "blender": (4, 40, 0),
    "description": "Allows to export meshes directly into the game.",
}

import math, subprocess
from enum import IntEnum
from pathlib import Path
import shutil

import bpy
from bpy.types import PropertyGroup, AddonPreferences
from bpy.props import StringProperty, IntProperty, FloatProperty, BoolProperty
from mathutils import Vector, Quaternion, Matrix

# --------------------------------------------------------------------------------
# Shape Classes+
class ShapeType(IntEnum):
    BILLBOARD = 0
    CUBOID = 1
    FLAT = 2
    MESH = 3
    CHARACTER = 4
    POINTER = 5
    DONTDRAW = 6

class ShapeEntry:
    """Represents an entry in the shape table"""

    def __init__(self, *args, **kwargs ):
        self.id = 0
        self.frame = 0
        self.is_shape_ref = False
        self.type = ShapeType.MESH
        self.scale = Vector((1,1,1))
        self.position = Vector((0,0,0))
        self.rotation = 0
        self.filepath = ""
        self.script="Default"

    def __str__(self):
        return f"<ShapeEntry {self.id:3d} Frame {self.frame:2d} Type {self.type.name}>"

    def to_line(self) -> str:
        line = f"{self.id} "
        line += f"{self.frame} "
        line += " ".join([f"{v}" for v in self.vals_01])
        line += f" {self.type} "
        line += f"{self.scale.x:g} {self.scale.y:g} {self.scale.z:g} "
        line += f"{self.position.x:g} {self.position.y:g} {self.position.z:g} "
        line += f"{self.rotation:g} "
        line += " ".join([f"{v}" for v in self.vals_02])
        line += f" {self.filepath} "
        line += " ".join([f"{v}" for v in self.vals_03])
        line += f" {self.script}"
        line += " \n"
        return line

    @staticmethod
    def from_line(line: str) -> None:
        se = ShapeEntry()
        values = line.strip().split(" ")
        se.id = int(values[0])
        se.frame = int(values[1])
        se.vals_01 = [int(v) for v in values[2:14]] # Todo: Find out, what these vals are

        se.type = ShapeType(int(values[14]))
        se.scale = Vector( (float(values[15]),float(values[16]), float(values[16]) ) )
        se.position = Vector( (float(values[18]),float(values[19]), float(values[20]) ) )
        se.rotation = float(values[21])
        
        se.vals_02 = [int(v) for v in values[22:28]] # Todo: Find out, what these vals are
        se.filepath = values[28]
        se.vals_03 = [int(v) for v in values[29:33]] # Todo: Find out, what these vals are
        try:
            se.script = values[33]
        except Exception as e:
            # print(f"WARNING: No script found for shape {values[0]}!")
            se.script = "default"
        return se


class ShapeTable:
    """Reads and writes the shape table. Now a singleton."""
    _instance = None

    def __init__(self):
        raise RuntimeError('Call instance() instead')

    @classmethod
    def instance(cls):
        if cls._instance is None:
            print('Creating new instance')
            cls._instance = cls.__new__(cls)
            cls.shapes = dict()
            cls.is_loaded = False
        return cls._instance

    def load(self, filepath, force=False):
        if self.is_loaded and not force:
            return
        self.shapes = dict()
        with open(filepath) as shapefile:
            for line in shapefile.readlines():
                shape_obj = ShapeEntry.from_line(line)
                if not shape_obj.id in self.shapes:
                    self.shapes[shape_obj.id] = []
                self.shapes[shape_obj.id].append(shape_obj)

    def save(self, filepath):
        lines=[]
        for so_id, frames in self.shapes.items():
            for frame in frames:
                lines.append(frame.to_line())

        with open(filepath, "w") as shapefile:
            shapefile.writelines(lines)

    def update_shapes(self, *shape_settings):
        for sh in shape_settings:
            if sh.shape_id not in self.shapes:
                print(f"Shape {sh.shape_id} not found in shapetable.dat")
                continue
            # print(f"{sh.shape_id}-{sh.frame}: {sh.shape_type} {sh.scale} {sh.mesh_path()}")
            # print(f"B {self.shapes[sh.shape_id][sh.frame].to_line()}")
            self.shapes[sh.shape_id][sh.frame].type = int(sh.shape_type)
            self.shapes[sh.shape_id][sh.frame].scale = sh.scale
            self.shapes[sh.shape_id][sh.frame].position = sh.position
            self.shapes[sh.shape_id][sh.frame].rotation = sh.rotation
            # print(f"A  {self.shapes[sh.shape_id][sh.frame].to_line()}")
            self.shapes[sh.shape_id][sh.frame].filepath = sh.mesh_path()

# --------------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------------

def select(*objs):
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = objs[0]
    for obj in objs:
        print(f"Selecting {obj.name}")
        obj.select_set(True)

def get_hierarchy(*objs):
    newobjs=[]    
    testobjs=list(objs)
    while testobjs:
        obj=testobjs.pop()
        testobjs.extend(obj.children)
        newobjs.append(obj)
    return newobjs

def model_to_filename(obj):
    """ Generates a standardized obj name """
    # <object name>_<shape number>x<frame number>
    return f"{obj.name.lower()}_{obj.uvii_export_settings.shape_id:004d}x{obj.uvii_export_settings.frame:002d}"

# def parent_to_filename(obj):
#     """ Generates a standardized obj name """
#     # <object name>_<shape number>x<frame number>
#     pobj = obj.parent
#     return f"{pobj.name.lower()}_{pobj.uvii_export_settings.shape_id:004d}x{pobj.uvii_export_settings.frame:002d}"

def full_export_filepath(obj):
    addon_prefs = bpy.context.preferences.addons["ultimavii_exporter"].preferences
    # return Path(addon_prefs.game_path) / "Models" / "3dmodels" / (parent_to_filename(obj)+obj.uvii_export_settings.format_suffix())
    # else:
    return Path(addon_prefs.game_path) / "Models" / "3dmodels" / (model_to_filename(obj)+obj.uvii_export_settings.format_suffix())

def add_to_modelnames(objname):
    """Writes the model name into the modelnames.txt file"""
    addon_prefs = bpy.context.preferences.addons["ultimavii_exporter"].preferences
    modelnames_filepath = Path(addon_prefs.game_path) / "Models" / "3dmodels" / "modelnames.txt"
    if not modelnames_filepath.exists():
        print(f"Could not find {modelnames_filepath}")
        return

    with open(modelnames_filepath) as modelfile:
        lines = [l.strip() for l in modelfile.readlines()]

    if not objname in lines:
        lines.append(objname)

    with open(modelnames_filepath, "w") as modelfile:
        modelfile.writelines( [f"{l}\n" for l in lines] )


def get_color_tex_path(mat):
    """ Returns an absolute path object of the base color if exists. """
    shader_node = None
    for n in mat.node_tree.nodes:
        if n.type == "BSDF_PRINCIPLED":
            shader_node = n
            break
    if shader_node == None:
        print("No Shader Node found in material '{mat.name}''.")
        return None
    base_color_input = None
    for i in n.inputs:
        if i.name == "Base Color":
            base_color_input = i
            break
    if base_color_input==None:
        print("No base color input found in material '{mat.name}''.")
        return None
    src_node = base_color_input.links[0].from_node
    if src_node==None:
        print("No base color node connected to material '{mat.name}''.")
        return None
    if src_node.type!="TEX_IMAGE":
        print("Base color node is not an image texture.")
        return None
    if src_node.image == None:
        print("Base color node has no image connected.")
        return None
    tex_path = Path(bpy.path.abspath(src_node.image.filepath)).resolve()
    if not tex_path.exists():
        print(f"Image file '{tex_path}' doesn't exist.")
        return None
    return tex_path

def replace_mdl_texture_entry(mtl_path, tex_path):
    lines = []
    with open(mtl_path) as mat_file:
        for line in mat_file.readlines():
            if line.startswith("map_Kd"):
                lines.append(f"map_Kd {tex_path.as_posix()}\n")
            else:
                lines.append(line)

    with open(mtl_path, "w") as mat_file:
        # mat_file.writelines( [f"{l} \n" for l in lines] )    
        mat_file.writelines( lines )

# --------------------------------------------------------------------------------
# Addon Prefs
# --------------------------------------------------------------------------------

class SCRIPTS_AP_uvii_settings(AddonPreferences):
    # this must match the add-on name, use '__package__'
    # when defining this in a submodule of a python package.
    bl_idname = "ultimavii_exporter"

    game_path: bpy.props.StringProperty(
        name="Game Path",
        description="Ultima VII Revisited Game Path",
        subtype="DIR_PATH",
        default="",
        maxlen=0
    )

    write_shapetable: bpy.props.BoolProperty(
        name="Shapetable",
        default=True,
        description="Write the object data to the shapetable.dat"
    )

    write_modelnames: bpy.props.BoolProperty(
        name="Modelnames",
        default=False,
        description="Write the object data to the modelnames.txt. DEPRECATED - Now loads every model."
    )

    copy_texture: bpy.props.BoolProperty(
        name="Copy the texture",
        default=True,
        description="Copy the texture to the model path."
    )

    def draw(self, context):
        self.layout.prop(self, "game_path")

# --------------------------------------------------------------------------------
# Object Settings
# --------------------------------------------------------------------------------

class SCRIPTS_PG_uvii_object_settings(PropertyGroup):
    
    is_uvii: bpy.props.BoolProperty(
        name="Is UVII asset",
        default=False,
        description="Is this an exportable asset."
    )

    export_path: bpy.props.StringProperty(
        name="Export Path",
        description="Where the file is exported to. DEPRECATED, is now generated from the object name.",
        default="",
        # subtype="FILE_PATH",
        subtype="NONE",
        maxlen=0
    )

    export_format : bpy.props.EnumProperty(
        name="Export Format",
        description="The file type it will be exported to.",
        # [(identifier, name, description, icon, number), ...].
        # Items: If icon, then you need the number at the end - doh!
        default="OBJ",
        items=[
            ("OBJ", "OBJ", "AliasWavefront OBJ (Doesn't support animations)."),
            ("GLTF", "GLTF", "GLTF (Not supported yet)"),
            ]
        )

    shape_id: bpy.props.IntProperty(
        name="Shape ID",
        default=0,
        description="The ID of the shape. Somewhere from 150 to 1023"
    )

    is_shape_ref: bpy.props.BoolProperty(
        name="Is Shape Reference",
        default=False,
        description="Is this a reference to another shape?"
    )

    frame: bpy.props.IntProperty(
        name="Frame Number",
        default=0,
        description="The animation frame. If not animated, set it to 0."
    )

    position: bpy.props.FloatVectorProperty(
        name="Tweak Pos",
        description="A position offset for the shape",
        default=(0.0, 0.0, 0.0),
        min=-100.0, max=100.0,  step=0.1,
        subtype="TRANSLATION"
    )

    scale: bpy.props.FloatVectorProperty(
        name="Tweak Dims",
        description="An additional scale for the shape.",
        default=(1, 1, 1),
        min=0.001, max=100.0,   step=0.1,
        subtype="XYZ"
    )

    rotation: IntProperty(
        name="rotation",
        description="The Rotation around the Up-Axis.",
        default=0,
        min=0, max=360,
        subtype="ANGLE"
    )

    shape_type : bpy.props.EnumProperty(
        name="DrawType",
        description="The draw type of the object. Probably should always be mesh.",
        # [(identifier, name, description, icon, number), ...].
        # Items: If icon, then you need the number at the end - doh!
        default="3",
        items=[
            ("0", "Billboard", "A simple camera facing image.", "MESH_PLANE", 0),
            ("1", "Cuboid", "A simple box", "MESH_CUBE", 1),
            ("2", "Flat Plane", "A flat plane on the ground", "MESH_PLANE", 2),
            ("3", "Mesh", "A fully meshed object.", "MONKEY", 3)
            ]
        )

    script_name: bpy.props.StringProperty(
        name="Script Name",
        description="My String.",
        default="Default",
        maxlen=0
    )

    def format_suffix(self):
        if self.export_format == "OBJ":
            return ".obj"
        elif self.export_format == "GLTF":
            return ".gltf"
        else:
            return ""

    def mesh_name(self):
        return Path(self.export_path).stem

    def mesh_path(self):
        addon_prefs = bpy.context.preferences.addons["ultimavii_exporter"].preferences
        base_gamepath = Path(addon_prefs.game_path)
        return Path(self.export_path).relative_to(base_gamepath).as_posix()

    # def shape(self):
    #     shape = ShapeEntry()
    #     shape.id = self.shape_id
    #     shape.frame = self.frame
    #     shape.is_shape_ref = self.is_shape_ref
    #     return self.update_shape(shape)

    # def update_shape(self, shape):
    #     shape.type = int(self.shape_type)
    #     shape.scale = self.scale
    #     shape.position = self.position
    #     shape.rotation = self.rotation
    #     shape.filepath = self.mesh_path()
    #     return shape

    # TODO: Add additional stuff

# --------------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------------

class SCRIPTS_OT_uvii_create_shape(bpy.types.Operator):
    """Create Shape"""
    bl_idname = "scripts.uvii_create_shape"
    bl_label = "Create Shape"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        context.active_object.uvii_export_settings.is_uvii = True
        return {'FINISHED'}

class SCRIPTS_OT_uvii_add_shape(bpy.types.Operator):
    """Create Shape"""
    bl_idname = "scripts.uvii_add_shape"
    bl_label = "Add another Shape"

    @classmethod
    def poll(cls, context):
        if context.active_object is None:
            return False
        return context.active_object.uvii_export_settings.is_uvii

    def execute(self, context):
        obj = context.active_object
        size = obj.dimensions.length*.03
        shape_count = len([o for o in obj.children if o.type=="EMPTY"])
        offset = Vector((obj.dimensions.x*.45, 0, obj.dimensions.z*.1*shape_count))
        bpy.ops.object.empty_add(type='SPHERE', align='WORLD', location=obj.location + offset)
        new_shape_obj = context.active_object
        new_shape_obj.uvii_export_settings.is_uvii = True
        new_shape_obj.uvii_export_settings.is_shape_ref = True
        new_shape_obj.name = obj.name+"_shape.001"
        new_shape_obj.empty_display_size = size
        select(obj, new_shape_obj)
        bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)
        select(new_shape_obj)
        new_shape_obj.uvii_export_settings.shape_id = obj.uvii_export_settings.shape_id
        new_shape_obj.uvii_export_settings.frame = obj.uvii_export_settings.frame
        new_shape_obj.uvii_export_settings.position = obj.uvii_export_settings.position
        new_shape_obj.uvii_export_settings.scale = obj.uvii_export_settings.scale
        new_shape_obj.uvii_export_settings.rotation = obj.uvii_export_settings.rotation
        new_shape_obj.uvii_export_settings.position = obj.uvii_export_settings.position
        return {'FINISHED'}

class SCRIPTS_OT_uvii_undo_shape(bpy.types.Operator):
    """Delete Shape Data"""
    bl_idname = "scripts.uvii_undo_shape"
    bl_label = "Delete Shape Data"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        context.active_object.uvii_export_settings.is_uvii = False
        return {'FINISHED'}

class SCRIPTS_OT_uvii_select_filepath(bpy.types.Operator):
    """Select export filepath"""
    bl_idname = "scripts.uvii_select_filepath"
    bl_label = "Select export filepath"

    filter_glob: StringProperty(
        default="*.obj",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    )

    filepath: StringProperty()
    filename:  StringProperty()
    directory:  StringProperty()

    @classmethod
    def poll(cls, context):
        if context.active_object==None:
            return False
        return True

    def invoke(self, context, _event):
        """This is called before any window opens."""
        # set filepath to a default. This will be selected first.
        addon_prefs = context.preferences.addons["ultimavii_exporter"].preferences
        settings = context.active_object.uvii_export_settings
        if settings.export_path!="":
            self.filepath = settings.export_path
        else:
            model_path = Path(addon_prefs.game_path) / "Models" / "3dmodels" / (context.active_object.name+settings.format_suffix())
            self.filepath = str(model_path)
        if settings.export_format == "OBJ":
            self.filter_glob = "*.obj"
        elif settings.export_format == "GLTF":
            self.filter_glob = "*.gltf"
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        """This is called after the window opened."""
        print(f"Filepath: {self.filepath}")
        context.active_object.uvii_export_settings.export_path = self.filepath
        return {'FINISHED'}

class SCRIPTS_OT_uvii_export_asset(bpy.types.Operator):
    """Export Shape"""
    bl_idname = "scripts.uvii_export_asset"
    bl_label = "Export Shape"

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def execute(self, context):
        addon_prefs = context.preferences.addons["ultimavii_exporter"].preferences
        base_gamepath = Path(addon_prefs.game_path)
        obj = context.active_object
        # need to make sure active object is selected, otherwise exporting empty file!
        obj.select_set(True)        
        settings = obj.uvii_export_settings
        export_path = full_export_filepath(obj)
        settings.export_path = str(export_path)

        # export shape mesh
        bpy.ops.wm.obj_export(
            filepath=settings.export_path, 
            check_existing=False, 
            apply_modifiers=True, 
            export_selected_objects=True,
            export_uv=True,
            export_normals=True,
            export_materials=True,
            export_triangulated_mesh=True)


        # fix shape mesh texture path
        if settings.export_format == "OBJ" and len(obj.data.materials)>0:
            mtl_path = Path(settings.export_path).with_suffix(".mtl")            
            tex_path = get_color_tex_path(obj.data.materials[0])
            if not mtl_path.exists():
                bpy.context.window_manager.popup_menu(
                    lambda self, ctx: ( [self.layout.label(text=x) for x in [f"{mtl_path} not found."]] ),
                    title="Warning", 
                    icon='ERROR')
                return {'CANCELLED'}
            if tex_path==None:
                bpy.context.window_manager.popup_menu(
                    lambda self, ctx: ( [self.layout.label(text=x) for x in [f"Couldn't find texture for {obj.name}"]] ),
                    title="Warning", 
                    icon='ERROR')   
                return {'CANCELLED'}
            else:
                if export_path.parent!=tex_path.parent:
                    if addon_prefs.copy_texture:
                        new_tex_path = export_path.with_name(tex_path.name)
                        print(f"Will copy texture from {tex_path} to {new_tex_path}!")
                        shutil.copy(tex_path, new_tex_path)
                        tex_path=new_tex_path
                    replace_mdl_texture_entry(mtl_path, tex_path.relative_to(base_gamepath))
                else:
                    bpy.context.window_manager.popup_menu(
                        lambda self, ctx: ( [self.layout.label(text=x) for x in ["Texture is not located in the model directory!", "It will not show up!"]] ),
                        title="Warning", 
                        icon='ERROR')

        # DEPRECATED add mesh name to modelnames.txt
        if addon_prefs.write_modelnames:
            add_to_modelnames(settings.mesh_name())

        # add shape data to shapetable.dat
        if addon_prefs.write_shapetable:
            # collect entries
            entries = []
            entries.append(settings)
            for o in obj.children:
                if o.uvii_export_settings.is_uvii and o.uvii_export_settings.is_shape_ref:
                    o.uvii_export_settings.export_path = str(export_path)
                    entries.append(o.uvii_export_settings)
            # update shapetable
            shapetable = ShapeTable.instance()
            shapetable.load(base_gamepath / "data" / "shapetable.dat")
            shapetable.update_shapes(*entries)
            shapetable.save(base_gamepath / "data" / "shapetable.dat")

        bpy.context.window_manager.popup_menu(
            lambda self, ctx: ( [self.layout.label(text=x) for x in [f"Successfully exported '{full_export_filepath(obj).name}"]] ),
            title="Info", 
            icon='INFO')

        return {'FINISHED'}

class SCRIPTS_OT_uvii_open_exported_file(bpy.types.Operator):
    """Open the exported file with the default viewer."""
    bl_idname = "scripts.uvii_open_exported_file"
    bl_label = "Open File"

    @classmethod
    def poll(cls, context):       
        if not context.active_object.uvii_export_settings.is_uvii:
            return False
        return True

    def execute(self, context):
        settings = context.active_object.uvii_export_settings
        subprocess.Popen(settings.export_path, shell=True)
        return {'FINISHED'}

class SCRIPTS_OT_uvii_open_explorer_to_file(bpy.types.Operator):
    """Open an Explorer Window to the file"""
    bl_idname = "scripts.uvii_open_explorer_to_file"
    bl_label = "Show in Explorer"

    @classmethod
    def poll(cls, context):
        if not context.active_object.uvii_export_settings.is_uvii:
            return False
        return True

    def execute(self, context):
        settings = context.active_object.uvii_export_settings
        print(f'explorer /select,"{settings.export_path}"')
        subprocess.Popen(f'explorer /select,"{settings.export_path}"')
        return {'FINISHED'}

class SCRIPTS_OT_uvii_start_game(bpy.types.Operator):
    """Open the exported file with the default viewer."""
    bl_idname = "scripts.uvii_start_game"
    bl_label = "Start the Game Executeable"

    @classmethod
    def poll(cls, context):
        addon_prefs = context.preferences.addons["ultimavii_exporter"].preferences
        if addon_prefs==None:
            return False
        if addon_prefs.game_path=="":
            return False
        game_path = Path(addon_prefs.game_path)
        if not game_path.exists():
            return False
        if not (game_path / "U7Revisited.exe").exists():
            return False
        return True

    def execute(self, context):
        addon_prefs = context.preferences.addons["ultimavii_exporter"].preferences
        game_exe = Path(addon_prefs.game_path) / "U7Revisited.exe"
        subprocess.Popen(str(game_exe), cwd=addon_prefs.game_path, shell=True)
        return {'FINISHED'}

# --------------------------------------------------------------------------------
# User Interface
# --------------------------------------------------------------------------------

class SCRIPTS_PT_uvii_user_interface(bpy.types.Panel):
    bl_space_type="VIEW_3D"
    bl_region_type="UI"
    bl_category="UVII Revisited"
    bl_label="UVII Revisited Exporter"

    def draw(self, context):
        accepted_types = ["MESH", "EMPTY"]

        box = self.layout.box()
        addon_prefs = context.preferences.addons["ultimavii_exporter"].preferences
        if addon_prefs.game_path=="":
            box.label(text="No game path set in prefs.")
            return
        game_path = Path(addon_prefs.game_path)
        if not game_path.exists():
            box.label(text="Game path doesn't exist.")
            return
        if not (game_path / "U7Revisited.exe").exists():
            box.label(text="Game exec doesn't exist at game path.")
            box.label(text="Are you sure the game path is correct?")
            return            
        if context.active_object == None:
            box.label(text="Nothing selected.")
            return
        settings = context.active_object.uvii_export_settings
        if context.active_object.type!="MESH" and not settings.is_shape_ref:
            box.label(text="Not a mesh.")
            return
        if not context.active_object.uvii_export_settings.is_uvii:
            box.label(text="Not an asset.")
            box.operator("scripts.uvii_create_shape")
            return

        # split = box.split(factor=.9, align=True)
        # split.prop(settings, "export_path")
        # split.operator("scripts.uvii_select_filepath", text="", icon="FILE_FOLDER")
        if not settings.is_shape_ref:
            box.label(text=f"Export Name:   \"{model_to_filename(context.active_object)}\"")
        box.prop(settings, "export_format")
        split = box.split()
        split.prop(settings, "shape_id")
        split.prop(settings, "frame")
        box.prop(settings, "shape_type")
        row = box.split()
        row.prop(settings, "position")
        row.prop(settings, "scale")
        box.prop(settings, "rotation")
        if settings.is_shape_ref:
            return
        split = box.split()
        # split.prop(addon_prefs, "write_modelnames")
        split.prop(addon_prefs, "write_shapetable")
        split.prop(addon_prefs, "copy_texture")
        split = box.split(factor=.9)
        split.operator("scripts.uvii_export_asset")
        split.operator("scripts.uvii_undo_shape", text="", icon="X")
        box.separator(type="LINE")
        if context.active_object.type=="MESH":
            box.operator("scripts.uvii_add_shape", icon="ADD")
        row = box.split()
        row.operator("scripts.uvii_open_exported_file", icon="FILE_3D")
        row.operator("scripts.uvii_open_explorer_to_file", icon="FILE_FOLDER")
        box.operator("scripts.uvii_start_game", icon="GHOST_ENABLED")


# --------------------------------------------------------------------------------
# Register and Init
# --------------------------------------------------------------------------------

blender_classes=[
    SCRIPTS_AP_uvii_settings,
    SCRIPTS_OT_uvii_create_shape,
    SCRIPTS_OT_uvii_add_shape,
    SCRIPTS_OT_uvii_undo_shape,
    SCRIPTS_OT_uvii_select_filepath,
    SCRIPTS_OT_uvii_export_asset,
    SCRIPTS_PG_uvii_object_settings,
    SCRIPTS_OT_uvii_open_exported_file,
    SCRIPTS_OT_uvii_open_explorer_to_file,
    SCRIPTS_OT_uvii_start_game,
    SCRIPTS_PT_uvii_user_interface
]

def register():
    for blender_class in blender_classes:
        bpy.utils.register_class(blender_class)
    bpy.types.Object.uvii_export_settings = bpy.props.PointerProperty(type = SCRIPTS_PG_uvii_object_settings)

def unregister():
    del bpy.types.Object.uvii_export_settings
    for blender_class in reversed(blender_classes):
        bpy.utils.unregister_class(blender_class)

if __name__ == "__main__":
    register()

    print("------------ New Round ------------")

    base_gamepath = Path(r"A:\Ultima7Revisited\Redist")

    # lines = [
    #     "889 0 0 0 8 8 0 8 8 33 8 0 33 8 0 1 1 1 0 0 0 0 1 2 2 3 3 1 Models/3dmodels/zzwrongcube.obj 1 0 889 0 func_0379 ",
    #     "889 1 0 0 8 8 0 8 8 33 8 0 33 8 0 1 1 1 0 0 0 0 1 2 2 3 3 1 Models/3dmodels/zzwrongcube.obj 1 0 889 1 func_0379 ",
    #     "889 2 0 0 8 8 0 8 8 31 8 0 32 8 0 1 1 1 0 0 0 0 1 2 2 3 3 1 Models/3dmodels/zzwrongcube.obj 1 0 889 2 func_0379 ",
    #     "889 3 0 0 8 8 0 8 8 31 8 0 32 8 0 1 1 1 0 0 0 0 1 2 2 3 3 1 Models/3dmodels/zzwrongcube.obj 1 0 889 3 default "
    # ]
    # sobjs = [ShapeEntry.from_line(sobj) for sobj in lines]
    # i = 0 
    # for so in sobjs:
    #     print(so.vals_03)
    #     print(so.script)
    #     print(lines[i])
    #     i+=1
    #     print(so.to_line())


    # shapetable = ShapeTable.instance()
    # shapetable.load(base_gamepath / "data" / "shapetable.dat")
    # print(f"Found {len(shapetable.shapes)} shape entries.")
    # print("889 0 0 0 8 8 0 8 8 33 8 0 33 8 0 1 1 1 0 0 0 0 1 2 2 3 3 1 Models/3dmodels/zzwrongcube.obj 1 0 889 0 func_0379 ")
    # print(shapetable.shapes[889][0].to_line())
    # shapetable.save(base_gamepath / "data" / "shapetable.new")
