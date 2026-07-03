"""What does the MetaHumanCharacter plugin expose to Python? Creation scriptability probe."""
import unreal

names = [n for n in dir(unreal) if "metahuman" in n.lower()]
unreal.log("MH CLASSES (%d): %s" % (len(names), ", ".join(sorted(names)[:40])))

# factories that could create a MetaHuman Character asset
factories = [n for n in names if "factory" in n.lower()]
unreal.log("MH FACTORIES: %s" % ", ".join(factories))

# editor subsystems
subs = [n for n in names if "subsystem" in n.lower() or "library" in n.lower() or "editor" in n.lower()]
unreal.log("MH SUBSYSTEMS/LIBS: %s" % ", ".join(subs))
