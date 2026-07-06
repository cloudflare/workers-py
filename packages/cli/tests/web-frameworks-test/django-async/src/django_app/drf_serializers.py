from rest_framework import serializers


class ItemSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    price = serializers.FloatField(min_value=0)
    quantity = serializers.IntegerField(min_value=0)
    tags = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )

    def validate_name(self, value):
        if value == "invalid":
            raise serializers.ValidationError("This name is not allowed")
        return value

    def validate(self, data):
        if data["price"] > 1000 and data["quantity"] > 100:
            raise serializers.ValidationError("bulk order too large")
        return data


class OrderItemSerializer(serializers.Serializer):
    product = serializers.CharField()
    quantity = serializers.IntegerField(min_value=1)


class OrderSerializer(serializers.Serializer):
    customer_name = serializers.CharField(max_length=100)
    items = OrderItemSerializer(many=True)
    notes = serializers.CharField(required=False, default="")

    def validate_items(self, value):
        if len(value) < 1:
            raise serializers.ValidationError("Must include at least one item")
        return value
