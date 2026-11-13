class User:
    def __init__(self, user_id=None, name="", email="", password="", role="customer", phone=""):
        self.user_id = user_id
        self.name = name
        self.email = email
        self.password = password
        self.role = role
        self.phone = phone or ""

    # Cafe Owner
    def is_cafe(self):
        return self.role.lower() == "cafe"
