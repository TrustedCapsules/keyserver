import os
import uuid
from dataclasses import dataclass
from typing import Tuple, Dict

from Cryptodome.Random import get_random_bytes
from flask import current_app
from jsonschema import validate
from jsonschema.exceptions import FormatError, ValidationError

import cgen
import crypto
import db
import mail


@dataclass
class RegisterRequest:
    email: str
    pubkey: str

    def __init__(self, data: Dict[str, str]) -> None:
        self.email = data['email']
        self.pubkey = data['pubkey']

    @staticmethod
    def is_valid(req: Dict[str, str]) -> bool:
        schema = {
            "type": "object",
            "properties": {
                "email": {"type": "string", "format": "email"},
                "pubkey": {"type": "string"},
            }
        }

        try:
            validate(instance=req, schema=schema)
            return True
        except FormatError:
            print('jsonschema format err')
            return False
        except ValidationError:
            print('jsonschema validation err')
            return False

    # saves hex(nonce) to db, returns an hex(encrypt(nonce)) and success bool
    def insert(self) -> Tuple[str, bool]:
        nonce = get_random_bytes(16)
        session = db.get_session()
        email = db.Email(email=self.email)
        device = db.Device(pubkey=self.pubkey, email=self.email, nonce=nonce.hex(), is_auth=False)
        session.add_all([email, device])
        try:
            session.commit()
            hex_encrypted_nonce = crypto.encrypt_rsa(nonce, self.pubkey).hex()
            mail.send_nonce(self.email, hex_encrypted_nonce)
            return hex_encrypted_nonce, True
        except Exception as e:
            print(e)
            session.rollback()
            return "", False
        finally:
            session.close()


@dataclass
class VerifyRequest:
    email: str
    pubkey: str
    nonce: str  # should receive hex(decrypt(fromhex(enc_nonce))) from trustzone

    def __init__(self, data: Dict[str, str]) -> None:
        self.email = data['email']
        self.pubkey = data['pubkey']
        self.nonce = data['nonce']

    @staticmethod
    def is_valid(req: Dict[str, str]) -> bool:
        schema = {
            "type": "object",
            "properties": {
                "email": {"type": "string", "format": "email"},
                "pubkey": {"type": "string"},
                "nonce": {"type": "string"},
            }
        }

        try:
            validate(instance=req, schema=schema)
            return True
        except FormatError:
            print('jsonschema format err')
            return False
        except ValidationError:
            print('jsonschema validation err')
            return False

    def authorize(self) -> bool:
        session = db.get_session()
        device = session.query(db.Device).filter(db.Device.pubkey == self.pubkey,
                                                 db.Device.email == self.email,
                                                 db.Device.nonce == self.nonce).first()
        if device is None:
            session.close()
            return False

        device.is_auth = True
        try:
            session.commit()
            return True
        except Exception as e:
            print(e)
            session.rollback()
            return False
        finally:
            session.close()


@dataclass
class CapsuleRequest:
    email1: str
    email2: str
    capsule_name: str
    invite_recipients: bool

    def __init__(self, data: Dict[str, str], capsule_name: str) -> None:
        self.email1 = data['email1']
        self.email2 = data['email2']
        self.capsule_name = capsule_name
        self.invite_recipients = (data['inviteRecipients'] == 'true')

    @staticmethod
    def is_valid(req: Dict[str, str], capsule_name: str) -> bool:
        schema = {
            "type": "object",
            "properties": {
                "email1": {"type": "string", "format": "email"},
                "email2": {"type": "string", "format": "email"},
                "inviteRecipients": {
                    "type": "string",
                    "pattern": "^(true)$|^(false)$"
                },  # should be bool, html makes it a string
            }
        }

        with current_app.app_context():
            capsule_path = os.path.join(current_app.config['CAPSULE_TEMP_WORK_PATH'], capsule_name)
            if not os.path.isdir(capsule_path) or \
                    not os.path.isfile(os.path.join(capsule_path, capsule_name + '.policy')) or \
                    not os.path.isfile(os.path.join(capsule_path, capsule_name + '.data')):
                return False

        try:
            validate(instance=req, schema=schema)
            return True
        except FormatError:
            print('jsonschema format err')
            return False
        except ValidationError:
            print('jsonschema validation err')
            return False

    # returns a file path to a generated capsule, and success bool
    def insert(self) -> Tuple[str, bool]:
        with current_app.app_context():
            cap_uuid = uuid.uuid4().hex
            out_file_name, ok = cgen.execute_cgen(self.capsule_name, cap_uuid)
            if not ok:
                return "", False

            session = db.get_session()
            recip1 = db.CapsuleRecipient(uuid=cap_uuid, email=self.email1)
            recip2 = db.CapsuleRecipient(uuid=cap_uuid, email=self.email2)
            decrypt_key = get_random_bytes(16).hex()
            cap = db.Capsule(uuid=cap_uuid, decrypt_key=decrypt_key, recipients=[recip1, recip2])
            session.add_all([cap, recip1, recip2])
            try:
                session.commit()
                #TODO: email uninvited recipients
                #mail.send_invite(recipient_email: str)
                return out_file_name, True
            except Exception as e:
                print(e)
                session.rollback()
                return "", False
            finally:
                session.close()


@dataclass
class DecryptRequest:
    uuid: str  # stored in capsule file
    pubkey: str

    def __init__(self, data: Dict[str, str]) -> None:
        self.uuid = data['uuid']
        self.pubkey = data['pubkey']

    @staticmethod
    def is_valid(req: Dict[str, str]) -> bool:
        schema = {
            "type": "object",
            "properties": {
                "uuid": {"type": "string"},
                "pubkey": {"type": "string"},
            }
        }

        try:
            validate(instance=req, schema=schema)
            return True
        except FormatError:
            print('jsonschema format err')
            return False
        except ValidationError:
            print('jsonschema validation err')
            return False

    # returns decrypt key and success bool
    def get_key(self) -> Tuple[str, bool]:
        session = db.get_session()
        capsule = session.query(db.Capsule) \
            .join(db.CapsuleRecipient, db.Capsule.uuid == db.CapsuleRecipient.uuid) \
            .join(db.Device, db.CapsuleRecipient.email == db.Device.email) \
            .filter(db.Capsule.uuid == self.uuid,
                    db.Device.pubkey == self.pubkey,
                    db.Device.is_auth == True).first()

        if capsule is None:
            session.close()
            return "", False

        return capsule.decrypt_key, True
