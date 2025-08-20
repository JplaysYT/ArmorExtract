import os
import glob
import shutil
from zipfile import ZipFile
from utils.utils import Utils

class Nexo:
    def __init__(self):
        self.furnace_data = {"items": {}}
        self.armor_types = ["HELMET", "CHESTPLATE", "LEGGINGS", "BOOTS"]
        self.assets_root = None  # resolved after unzip

    def extract(self):
        os.makedirs("output/nexo", exist_ok=True)

        # 1) Unzip and resolve assets root robustly
        zip_path = "Nexo/pack/pack.zip"
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"Missing zip: {zip_path}")
        with ZipFile(zip_path) as z:
            z.extractall("Nexo/pack")

        self.assets_root = self._find_assets_root("Nexo/pack")
        if not self.assets_root:
            raise RuntimeError("Could not locate an 'assets' folder under Nexo/pack after extraction.")

        # 2) Load YAMLs safely
        data_files = glob.glob("Nexo/items/**/*.yml", recursive=True)
        if not data_files:
            print("[WARN] No YAML files found under Nexo/items/**.yml")

        for file in data_files:
            data = Utils.load_yaml(file)
            if not isinstance(data, dict):
                print(f"[WARN] Skipping YAML (not a dict or empty): {file}")
                continue

            for item_id, item in data.items():
                if not isinstance(item, dict):
                    print(f"[WARN] {file} -> item '{item_id}' is not a dict; skipping")
                    continue

                material = item.get("material") or ""
                pack = item.get("Pack") or {}  # tolerate null
                if not isinstance(pack, dict):
                    print(f"[WARN] {file} -> item '{item_id}' has non-dict 'Pack'; skipping")
                    continue

                model_id = pack.get("custom_model_data")
                if model_id in (None, ""):
                    # No model id → nothing to map
                    continue

                # Only process armor materials
                if not any(t in material for t in self.armor_types):
                    continue

                # Gather textures (could be a string or a list)
                textures = pack.get("textures")
                if isinstance(textures, str):
                    textures = [textures]
                elif not isinstance(textures, list):
                    textures = []

                fallback_tex = pack.get("texture")
                if fallback_tex:
                    textures.append(fallback_tex)

                # normalize list: remove falsy & duplicates preserving order
                seen = set()
                textures = [t for t in textures if t and not (t in seen or seen.add(t))]
                if not textures:
                    print(f"[WARN] {file} -> item '{item_id}' has no textures; skipping")
                    continue

                armor_type = self.get_armor_type(material).lower()

                for tex in textures:
                    texture_path = self.build_texture_path(tex, armor_type)  # relative path under assets
                    full_src = os.path.join(self.assets_root, texture_path)

                    if not os.path.exists(full_src):
                        # Try to find a close alternative
                        alt = self.find_alternative_path(texture_path)
                        if not alt:
                            print(f"[WARN] Missing texture: {texture_path} (looked under {self.assets_root})")
                            continue
                        full_src = alt
                        # Recompute the relative texture path under assets for Geyser furnace.json
                        texture_path = os.path.relpath(full_src, self.assets_root).replace("\\", "/")

                    # Copy to output
                    dst_path = os.path.join("output/nexo/textures/models", texture_path)
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    shutil.copy(full_src, dst_path)

                    # Insert into furnace mapping (stringify model id for JSON safety)
                    self.furnace_data["items"] \
                        .setdefault(f"minecraft:{material}".lower(), {}) \
                        .setdefault("custom_model_data", {})[str(model_id)] = {
                            "armor_layer": {
                                "type": armor_type,
                                "texture": f"textures/models/{texture_path}",
                                "auto_copy_texture": False
                            }
                        }

        Utils.save_json("output/nexo/furnace.json", self.furnace_data)

    # ---------- helpers ----------

    def _find_assets_root(self, root_dir: str) -> str | None:
        """
        After extracting the zip, find the first directory that looks like an 'assets' root,
        e.g., Nexo/pack/assets or Nexo/pack/SomeFolder/assets, etc.
        """
        # exact match first
        direct = os.path.join(root_dir, "assets")
        if os.path.isdir(direct):
            return direct

        # fallback: search for 'assets' folder anywhere under root_dir
        for path in glob.glob(os.path.join(root_dir, "**", "assets"), recursive=True):
            if os.path.isdir(path):
                return path
        return None

    def get_armor_type(self, material: str) -> str:
        return next((t for t in self.armor_types if t in (material or "")), "UNKNOWN")

    def build_texture_path(self, tex: str, armor_type: str) -> str:
        """
        Convert a Nexo texture reference into an assets-relative path that points to a PNG
        for the armor layer.

        Examples:
          - "minecraft:foo/bar_baz" -> "minecraft/textures/foo/bar_armor_layer_1.png"
          - "custompack:my_ns/my_helmet" -> "custompack/textures/my_ns/my_armor_layer_1.png"
          - "foo/bar" (no namespace) -> "minecraft/textures/foo/bar_armor_layer_1.png"
        """
        base = tex.replace(":", "/textures/") if ":" in tex else f"minecraft/textures/{tex}"
        layer = "layer_2" if "leggings" in (armor_type or "") else "layer_1"
        # use the prefix up to the first underscore to construct "{prefix}_armor_layer_X.png"
        fname = os.path.basename(base)
        prefix = fname.split("_")[0] if "_" in fname else os.path.splitext(fname)[0]
        return f"{os.path.dirname(base)}/{prefix}_armor_{layer}.png"

    def find_alternative_path(self, original_path: str) -> str | None:
        """
        Try a fuzzier glob to find a similarly-named armor texture if the exact path isn't present.
        E.g., turn "ns/textures/foo/bar_armor_layer_1.png" into
              "ns/textures/foo/{prefix}**_armor_layer_1.png"
        """
        base = os.path.basename(original_path)
        dirname = os.path.dirname(original_path)
        if "_" in base:
            head, tail = base.split("_", 1)
        else:
            head, tail = os.path.splitext(base)[0], base

        pattern = f"{dirname}/{head}**_{tail}"
        matches = glob.glob(os.path.join(self.assets_root, pattern), recursive=True)
        return matches[0] if matches else None
