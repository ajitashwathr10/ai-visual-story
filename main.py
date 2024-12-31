import os
import json
import torch
import numpy as np
from PIL import Image
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Union
from dataclasses import dataclass, asdict
import spacy
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    AutoModelForTokenClassification,
    Pipeline
)
from torch.nn import functional as F
import logging
from enum import Enum
import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level = logging.INFO)
logger = logging.getLogger(__name__)

class StorytellingException(Exception):
    pass

class ProcessingError(StorytellingException):
    pass

class LayoutError(StorytellingException):
    pass

class ImageGenerationError(StorytellingException):
    pass

class StorageError(StorytellingException):
    pass

@dataclass
class Entity:
    name: str
    type: str
    attributes: Dict[str, str]
    position: Optional[Dict[str, float]] = None
    importanc: float = 1.0

    def to_dict(self) -> Dict:
        return asdict(self)
    
class EmotionType(Enum):
    HAPPY = "happy"
    SAD = "sad"
    NEUTRAL = "neutral"
    ANGRY = "angry"
    SURPRISE = "surprise"
    FEAR = "fear"
    DISGUST = "disgust"
    CONFUSED = "confused"
    OTHER = "other"

    @classmethod
    def from_string(cls, emotion: str) -> 'EmotionType':
        try:
            return cls(emotion.lower())
        except ValueError:
            return cls.OTHER
@dataclass
class Scene:
    id: int
    text: str
    entities: List[Entity]
    mood: EmotionType
    actions: List[str]
    layout: Optional[Dict] = None
    image_path: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'text': self.text,
            'entities': [e.to_dict() for e in self.entities],
            'mood': self.mood.value,
            'actions': self.actions,
            'layout': self.layout,
            'image_path': self.image_path
        }

class TextProcesor:
    def __init__(self):
        try:
            self.nlp = spacy.load("en_core_web_lg")
            self.tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
            self.emotion_model = AutoModelForSequenceClassification.from_pretrained("microsoft/bert-base-uncased-emotion")
            logging.info("Successfully initialized NLP models")
        except Exception as e:
            logging.error(f"Failed to initialize NLP models: {e}")
            raise ProcessingError("Failed to initialize NLP models")
    def segment_scenes(self, text: str) -> List[str]:
        try: 
            doc = self.nlp(text)
            scenes = []
            current_scene = []
            for sent in doc.sents:
                current_scene.append(sent.text)
                if any(marker in sent.text.lower() for marker in
                       ["later", "meanwhile", "after", "before", "next", "suddenly"]):
                    scenes.append(" ".join(current_scene))
                    current_scene = []
            if current_scene:
                scenes.append(" ".join(current_scene))
            return scenes if scenes else [text]
        except Exception as e:
            logging.error(f"Failed to segment scenes: {e}")
            raise ProcessingError("Failed to segment scenes")
        
    def extract_entities(self, text: str) -> List[Entity]:
        try:
            doc = self.nlp(text)
            entities = []
            for ent in doc.ents:
                importance = 1.0
                if ent.label_ in ["PERSON", "ORG"]:
                    importance *= 1.5
                attributes = {
                    "description": self._get_entity_description(ent, doc),
                    "label": ent.label_
                }
                entities.append(Entity(
                    name = ent.text,
                    type = ent.label_,
                    attributes = attributes,
                    importance = importance
                ))
            return entities
        except Exception as e:
            logging.error(f"Entity extraction failed: {str(e)}")
            raise ProcessingError(f"Entity extraction failed: {str(e)}")
    
    def _get_entity_description(self, ent, doc) -> str:
        description_terms = []
        for token in doc:
            if token.head == ent.root:
                if token.dep_ in ["amod", "advmod"]:
                    description_terms.append(token.text)
        return " ".join(description_terms) if description_terms else ""
    
    def detect_actions(self, text: str) -> List[str]:
        try:
            doc = self.nlp(text)
            actions = []
            for token in doc:
                if token.pos_ == "VERB" and token.dep_ in ["ROOT", "xcomp"]:
                    verb_phrase = self._extract_verb_phrase(token)
                    if verb_phrase:
                        actions.append(verb_phrase)
            return actions
        except Exception as e:
            logger.error(f"Action detection failed: {str(e)}")
            raise ProcessingError(f"Action detection failed: {str(e)}")
    
         


