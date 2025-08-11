import os
import glob
import shutil
from utils.utils import Utils

class ItemsAdder:
    def __init__(self):
        self.armors_rendering = {}
        self.furnace_data = {"items": {}}
        self.item_ids = Utils.load_yaml("ItemsAdder/storage/items_ids_cache.yml") or {}
        if not isinstance(self.item_ids, dict):
            self.item_ids = {}
        if not self.item_ids:
            print("[WARN] items_ids_cache.yml not found or empty; no items will be mapped.")

    def extract(self):
        os.makedirs("output/itemsadder", exist_ok=True)

        datas = []
        for file in glob.glob("ItemsAdder/contents/**/*.yml", recursive=True):
            data = Utils.load_yaml(file)
            if isinstance(data, dict):
                datas.append(data)
            else:
                print(f"[WARN] Skipping YAML (not a dict): {file}")

        # Collect armors_rendering and enrich from equipments
        for data in datas:
            # Merge armors_rendering only if it's a dict of dicts
            ar = data.get("armors_rendering")
            if isinstance(ar, dict):
                for k, v in ar.items():
                    if isinstance(v, dict):
                        self.armors_rendering[k] = v
                    else:
                        print(f"[WARN] armors_rendering entry for {k} is not a dict; skipping")

            namespace = (data.get("info") or {}).get("namespace", "") or ""
            eq = data.get("equipments") or {}
            if not isinstance(eq, dict):
                continue
            for equip_id, equip_data in eq.items():
                if not isinstance(equip_data, dict):
                    print(f"[WARN] equipment {equip_id} is not a dict; skipping")
                    continue
                if equip_data.get("type") == "armor" or ("layer_1" in equip_data):
                    key = f"{namespace}:{equip_id}" if namespace else str(equip_id)
                    self.armors_rendering[key] = {
                        "layer_1": equip_data.get("layer_1", ""),
                        "layer_2": equip_data.get("layer_2", ""),
                    }

        # Build furnace data
        for data in datas:
            namespace = (data.get("info") or {}).get("namespace", "") or ""
            items = data.get("items") or {}
            if not isinstance(items, dict):
                continue

            for item_id, item_data in items.items():
                if not isinstance(item_data, dict):
                    print(f"[WARN] item {item_id} is not a dict; skipping")
                    continue

                armor_type, layer = self.get_armor(
                    (item_data.get("specific_properties") or {}).get("armor", {}) .get("slot")
                    or (item_data.get("equipment") or {}).get("slot"),
                    item_data
                )
                if not armor_type:
                    continue

                material = (item_data.get("resource") or {}).get("material", f"LEATHER_{armor_type}")
                mat_map = self.item_ids.get(material)
                if not isinstance(mat_map, dict):
                    continue

                ns_key = f"{namespace}:{item_id}" if namespace else str(item_id)
                cmd_val = mat_map.get(ns_key)
                if cmd_val is None:
                    continue

                texture_path = self.get_texture(item_data, namespace, layer)
                if not texture_path:
                    continue

                texture_files = glob.glob(f"ItemsAdder/contents/**/textures/{texture_path}.png", recursive=True)
                if not texture_files:
                    continue

                output_path = f"output/itemsadder/textures/models/{texture_path}.png"
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                shutil.copy(texture_files[0], output_path)

                material_key = f"minecraft:{material}".lower()
                self.furnace_data["items"] \
                    .setdefault(material_key, {}) \
                    .setdefault("custom_model_data", {})[str(cmd_val)] = {
                        "armor_layer": {
                            "type": armor_type.lower(),
                            "texture": f"textures/models/{texture_path}",
                            "auto_copy_texture": False
                        }
                    }

        Utils.save_json("output/itemsadder/furnace.json", self.furnace_data)

    def get_armor(self, slot, item_data):
        slot_map = {
            "head": ("HELMET", "layer_1"),
            "chest": ("CHESTPLATE", "layer_1"),
            "legs": ("LEGGINGS", "layer_2"),
            "feet": ("BOOTS", "layer_1"),
        }
        if slot:
            result = slot_map.get(str(slot).lower())
            if result:
                return result

        material = (item_data.get("resource") or {}).get("material") or ""
        for armor in slot_map.values():
            if armor[0] in material:
                return armor
        return None, None

    def get_texture(self, item_data, namespace, layer):
        armor_data = (item_data.get("specific_properties") or {}).get("armor", {}) or {}

        # custom_armor path
        custom_armor = armor_data.get("custom_armor")
        if custom_armor:
            entry = self.armors_rendering.get(custom_armor)
            if isinstance(entry, dict):
                val = entry.get(layer)
                if val:
                    return val

        # equipment-based path
        equipment_id = (item_data.get("equipment") or {}).get("id")
        if equipment_id:
            if ":" not in str(equipment_id) and namespace:
                equipment_id = f"{namespace}:{equipment_id}"
            entry = self.armors_rendering.get(equipment_id)
            if isinstance(entry, dict):
                val = entry.get(layer)
                if val:
                    return val

        # fallback
        return (item_data.get("resource") or {}).get("model_path")
