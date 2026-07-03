"""Dye the default garments per character — muted tavern-period palette.
Real medieval clothing needs a FAB pack; this kills the gym-clothes look meanwhile."""
import unreal

mel = unreal.MaterialEditingLibrary
PALETTE = {
    # name: (shirt rgb, shorts rgb)
    "Della":  ((0.085, 0.055, 0.035), (0.050, 0.035, 0.025)),   # worn umber over dark brown
    "Corvin": ((0.045, 0.045, 0.050), (0.030, 0.030, 0.033)),   # charcoal
    "Edwin":  ((0.065, 0.085, 0.040), (0.055, 0.040, 0.028)),   # moss green over brown
    "Bri":    ((0.140, 0.045, 0.055), (0.045, 0.038, 0.033)),   # muted wine over gray-brown
}

for name, (shirt, short) in PALETTE.items():
    for garment, rgb in (("Shirt", shirt), ("Short", short)):
        mi = None
        for shape in ("A", "B", "C"):
            path = "/Game/Cast/Unpacked/%s/Clothing/MI_WI_DefaultGarment_M_DG_bodyShape%s_%s" % (name, shape, garment)
            if unreal.EditorAssetLibrary.does_asset_exist(path):
                mi = unreal.EditorAssetLibrary.load_asset(path)
                break
        if not mi:
            unreal.log("MISSING garment MI for %s %s" % (name, garment))
            continue
        c = unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0)
        for p in ("diffuse_color_1", "diffuse_color_2", "B_diffuse_color_1"):
            mel.set_material_instance_vector_parameter_value(mi, p, c)
        mel.update_material_instance(mi)
        unreal.EditorAssetLibrary.save_asset(path)
        unreal.log("%s %s dyed" % (name, garment))
unreal.log("GARMENTS DYED")
