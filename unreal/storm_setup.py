"""Storm dressing: import the rain loop, ambient rain sound in the taproom, dim stormy light,
navmesh volume over the tavern so minds' movement choices actually path."""
import unreal

at = unreal.AssetToolsHelpers.get_asset_tools()
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# 1) rain loop import
task = unreal.AssetImportTask()
task.set_editor_property("filename", r"C:\Users\Alejandro\Downloads\rain_loop.wav")
task.set_editor_property("destination_path", "/Game/Audio")
task.set_editor_property("automated", True)
task.set_editor_property("save", True)
task.set_editor_property("replace_existing", True)
at.import_asset_tasks([task])
rain = unreal.EditorAssetLibrary.load_asset("/Game/Audio/rain_loop")
if rain:
    rain.set_editor_property("looping", True)
    rain.set_editor_property("volume", 0.35)
    unreal.EditorAssetLibrary.save_asset("/Game/Audio/rain_loop")
    unreal.log("rain loop imported + looping")

# 2) ambient sound actor in the taproom (rain on the roof)
existing = [a for a in eas.get_all_level_actors() if a.get_actor_label() == "RainAmbience"]
if not existing and rain:
    amb = eas.spawn_actor_from_class(unreal.AmbientSound, unreal.Vector(-80.0, 150.0, 350.0), unreal.Rotator(0, 0, 0))
    amb.set_actor_label("RainAmbience")
    ac = amb.get_editor_property("audio_component")
    ac.set_editor_property("sound", rain)
    ac.set_editor_property("volume_multiplier", 0.9)
    unreal.log("RainAmbience placed")

# 3) stormy light: find the directional light, dim + cool it
for a in eas.get_all_level_actors():
    if a.get_class().get_name() == "DirectionalLight":
        lc = a.get_editor_property("light_component")
        before = lc.get_editor_property("intensity")
        lc.set_editor_property("intensity", max(1.0, before * 0.35))
        lc.set_editor_property("light_color", unreal.Color(170, 185, 205, 255))
        unreal.log("directional dimmed: %.2f -> %.2f, cooled" % (before, max(1.0, before * 0.35)))

# 4) navmesh over the tavern interior
nav = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == "NavMeshBoundsVolume"]
if not nav:
    v = eas.spawn_actor_from_class(unreal.NavMeshBoundsVolume, unreal.Vector(-80.0, 0.0, 100.0), unreal.Rotator(0, 0, 0))
    v.set_actor_scale3d(unreal.Vector(15.0, 20.0, 3.0))   # default brush 200^3 -> covers the taproom
    unreal.log("NavMeshBoundsVolume placed")
else:
    unreal.log("navmesh volume already present")

ok = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()
unreal.log("level saved: %s" % ok)
