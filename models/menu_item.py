class MenuItem:
    def __init__(
        self,
        item_id=None,
        name="",
        category="",
        price=0.0,
        description="",
        available=True,
        image=None
    ):
        self.item_id = item_id
        self.name = name
        self.category = category
        self.price = float(price)
        self.description = description
        self.available = available
        self.image = image
