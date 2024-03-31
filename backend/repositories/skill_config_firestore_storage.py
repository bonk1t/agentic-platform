from firebase_admin import firestore
from google.cloud.firestore_v1 import FieldFilter

from backend.models.skill_config import SkillConfig


class SkillConfigFirestoreStorage:
    def __init__(self):
        self.db = firestore.client()
        self.collection_name = "skill_configs"

    def load_by_user_id(self, user_id: str | None = None) -> list[SkillConfig]:
        collection = self.db.collection(self.collection_name)
        query = collection.where(filter=FieldFilter("user_id", "==", user_id))
        return [SkillConfig.model_validate(document_snapshot.to_dict()) for document_snapshot in query.stream()]

    def load_by_id(self, id_: str) -> SkillConfig | None:
        collection = self.db.collection(self.collection_name)
        document_snapshot = collection.document(id_).get()
        if not document_snapshot.exists:
            return None
        return SkillConfig.model_validate(document_snapshot.to_dict())

    def load_by_titles(self, titles: list[str]) -> list[SkillConfig]:
        collection = self.db.collection(self.collection_name)
        # Firestore `in` query supports up to 10 items in the array.
        if len(titles) > 10:
            raise ValueError("Titles list exceeds the maximum size of 10 for an 'in' query in Firestore.")

        query = collection.where(filter=FieldFilter("title", "in", titles))
        results = [SkillConfig.model_validate(document_snapshot.to_dict()) for document_snapshot in query.stream()]
        return results

    def save(self, skill_config: SkillConfig) -> tuple[str, int]:
        collection = self.db.collection(self.collection_name)
        if skill_config.id is None:
            # Create a new document and set the id
            document_reference = collection.add(skill_config.model_dump())[1]
            skill_config.id = document_reference.id
        collection.document(skill_config.id).set(skill_config.model_dump())

        return skill_config.id, skill_config.version
