

const trackingSteps = ['placed', 'packing', 'shipped', 'delivered'];
String prettyStatus(String value) {
  switch (value) {
    case 'placed': return 'Order placed';
    case 'packing': return 'Preparing your order';
    case 'shipped': return 'Shipped';
    case 'delivered': return 'Delivered';
    default: return value;
  }
}

