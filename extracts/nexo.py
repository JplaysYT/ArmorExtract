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
                    dst_path = os.path.join("output/nexo/text_
