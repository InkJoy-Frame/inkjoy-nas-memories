import requests

SERVERS = {
    'global': 'https://openapi.inkjoyframe.com',
    'china': 'https://openapi.advisor.epaperframe.com',
}


class InkJoyClient:
    def __init__(self, server_url, token=None):
        self.server_url = server_url.rstrip('/')
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'InkJoyManager/1.0'})
        if token:
            self.session.headers['Authorization'] = f'Bearer {token}'

    def login(self, email, password):
        resp = self.session.post(
            f'{self.server_url}/api/v1/auth/login',
            json={'email': email, 'password': password},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get('code') == 0:
            self.token = data['data']['token']
            self.session.headers['Authorization'] = f'Bearer {self.token}'
            return data['data']
        raise Exception(data.get('msg', '登录失败'))

    def get_devices(self):
        resp = self.session.get(f'{self.server_url}/api/v1/devices', timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get('code') == 0:
            return data.get('data', [])
        raise Exception(data.get('msg', '获取设备列表失败'))

    def publish_image(self, device_id, image_data, filename='image.jpg'):
        files = {'file': (filename, image_data, 'image/jpeg')}
        resp = self.session.post(
            f'{self.server_url}/api/v1/devices/{device_id}/publish',
            files=files,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get('code') == 0:
            return data.get('data')
        raise Exception(data.get('msg', '发布图片失败'))
