import os
import tempfile

import pytest
from werkzeug.datastructures import FileStorage

import cgen
import crypto
import req_handler
from backend import keyserver
from backend.req_models import RegisterRequest, VerifyRequest, CapsuleRequest, DecryptRequest


@pytest.fixture
def client():
    db_fd, keyserver.app.config['DATABASE'] = tempfile.mkstemp()
    keyserver.app.config['TESTING'] = True
    client = keyserver.app.test_client()

    with keyserver.app.app_context():
        keyserver.init_db()

    yield client
    os.close(db_fd)
    os.unlink(keyserver.app.config['DATABASE'])


def test_register_request(client):
    with keyserver.app.app_context():
        form_data = {"email": "a@email.com",
                     "pubkey": open("backend_tests/demo_rsakey_pem.pub", "r").read()}
        assert RegisterRequest.is_valid(form_data)
        reg_req = RegisterRequest(form_data)
        nonce, ok = reg_req.insert()
        assert len(nonce) > 0 and ok


def test_verify_request(client):
    with keyserver.app.app_context():
        reg_form_data = {"email": "a@email.com",
                         "pubkey": open("backend_tests/demo_rsakey_pem.pub", "r").read()}
        reg_req = RegisterRequest(reg_form_data)
        hex_enc_nonce, ok = reg_req.insert()
        assert len(hex_enc_nonce) > 0 and ok

        privkey = open("backend_tests/demo_rsakey", "r").read()
        verify_form_data = {"email": "a@email.com",
                            "pubkey": open("backend_tests/demo_rsakey_pem.pub", "r").read(),
                            "nonce": crypto.decrypt_rsa(bytes.fromhex(hex_enc_nonce), privkey).hex()}
        assert VerifyRequest.is_valid(verify_form_data)
        verify_req = VerifyRequest(verify_form_data)
        assert verify_req.authorize()


def test_capsule_request(client):
    with keyserver.app.app_context():
        cap_form_data = {"email1": "a@email.com",
                         "email2": "b@email.com",
                         "inviteRecipients": "true",
                         "policy": open("backend_tests/demo.lua", "rb"),
                         "data": open("backend_tests/demo.data", "rb")}

        capsule_name = req_handler.prep_capsule(FileStorage(stream=cap_form_data['policy']),
                                                FileStorage(stream=cap_form_data['data']))
        assert CapsuleRequest.is_valid(cap_form_data, capsule_name)
        cap_req = CapsuleRequest(cap_form_data, capsule_name)
        capsule_filename, ok = cap_req.insert()
        assert capsule_filename != '' and ok


def test_decrypt_request(client):
    with keyserver.app.app_context():
        # make device
        reg_form_data = {"email": "a@email.com",
                         "pubkey": open("backend_tests/demo_rsakey_pem.pub", "r").read()}
        reg_req = RegisterRequest(reg_form_data)
        hex_enc_nonce, ok = reg_req.insert()
        assert len(hex_enc_nonce) > 0 and ok

        # register it
        priv_key = open("backend_tests/demo_rsakey", "r").read()
        verify_form_data = {"email": "a@email.com",
                            "pubkey": open("backend_tests/demo_rsakey_pem.pub", "r").read(),
                            "nonce": crypto.decrypt_rsa(bytes.fromhex(hex_enc_nonce), priv_key).hex()}
        verify_req = VerifyRequest(verify_form_data)
        assert verify_req.authorize()

        # make capsule
        cap_form_data = {"email1": "a@email.com",
                         "email2": "b@email.com",
                         "inviteRecipients": "true",
                         "policy": open("backend_tests/demo.lua", "rb"),
                         "data": open("backend_tests/demo.data", "rb")}

        capsule_name = req_handler.prep_capsule(FileStorage(stream=cap_form_data['policy']),
                                                FileStorage(stream=cap_form_data['data']))
        cap_req = CapsuleRequest(cap_form_data, capsule_name)
        capsule_filename, ok = cap_req.insert()
        assert capsule_filename != '' and ok

        # request key
        uuid = cgen.get_capsule_uuid(capsule_filename)
        decrypt_form_data = {"uuid": uuid,
                             "pubkey": open("backend_tests/demo_rsakey_pem.pub", "r").read()}
        decrypt_req = DecryptRequest(decrypt_form_data)
        hex_key, ok = decrypt_req.get_key()
        assert len(hex_key) > 0 and ok
