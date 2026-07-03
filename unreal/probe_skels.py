import unreal

for n in ["Della", "Corvin", "Edwin", "Bri"]:
    m = unreal.EditorAssetLibrary.load_asset("/Game/Cast/Unpacked/%s/Body/SKM_MH_%s_BodyMesh" % (n, n))
    if m:
        unreal.log("%s: %s" % (n, m.get_editor_property("skeleton").get_path_name()))
    else:
        unreal.log("%s: body mesh missing" % n)
