import 'package:flutter/material.dart';
import '../../../core/legacy_palette.dart';
import '../../../core/money.dart';
import '../../../core/widgets/section_title.dart';
import '../../../core/widgets/total_row.dart';
import '../../catalogue/data/product.dart';
import '../../catalogue/ui/product_tile.dart';
import '../../checkout/ui/checkout_page.dart';
import '../../checkout/data/legacy_checkout_repository.dart';
import '../../orders/state/orders_store.dart';
import '../state/cart_store.dart';

class CartPage extends StatelessWidget {
  const CartPage({super.key, required this.products, required this.cart, required this.orders, required this.checkout});
  final Future<List<Product>> products;
  final CartStore cart;
  final OrdersStore orders;
  final LegacyCheckoutRepository checkout;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('My cart')),
    body: AnimatedBuilder(animation: cart, builder: (context, _) => bounded(
      FutureBuilder<List<Product>>(
        future: products,
        builder: (context, snapshot) {
          if (!snapshot.hasData) return Center(child: Text(snapshot.hasError ? 'Cannot load catalogue' : 'Loading...'));
          final selected = snapshot.data!.where((p) => cart.quantity(p.id) > 0).toList();
          final subtotal = selected.fold<int>(0, (sum, p) => sum + p.priceSen * cart.quantity(p.id));
          return ListView(padding: const EdgeInsets.all(18), children: [
            const SectionTitle('Shopping bag'),
            const SizedBox(height: 5),
            const Text('DEMO: Your cart is independent from the official Sagemaker shop.',
              style: TextStyle(color: Colors.black54)),
            const SizedBox(height: 18),
            if (selected.isEmpty) const Card(child: Padding(
              padding: EdgeInsets.all(30),
              child: Column(children: [Icon(Icons.shopping_bag_outlined, size: 50, color: forest),
                SizedBox(height: 10), Text('Your bag is empty')]),
            )),
            for (final p in selected)
              Card(child: Padding(padding: const EdgeInsets.all(12), child: Row(children: [
                ClipRRect(borderRadius: BorderRadius.circular(10), child: SizedBox(
                  width: 76, height: 76, child: ProductImage(product: p))),
                const SizedBox(width: 12),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(p.name, maxLines: 2, style: const TextStyle(color: deep, fontWeight: FontWeight.w800)),
                  const SizedBox(height: 4),
                  Text('${formatRm(p.priceSen)} demo / item', style: const TextStyle(color: Colors.black54, fontSize: 12)),
                  const SizedBox(height: 4),
                  Row(mainAxisSize: MainAxisSize.min, children: [
                    IconButton(tooltip: 'Decrease', visualDensity: VisualDensity.compact,
                      onPressed: () => cart.setQuantity(p.id, cart.quantity(p.id) - 1),
                      icon: const Icon(Icons.remove_circle_outline)),
                    Text('${cart.quantity(p.id)}', style: const TextStyle(fontWeight: FontWeight.bold)),
                    IconButton(tooltip: 'Increase', visualDensity: VisualDensity.compact,
                      onPressed: cart.quantity(p.id) < 20 ? () => cart.add(p.id) : null,
                      icon: const Icon(Icons.add_circle_outline)),
                  ]),
                ])),
                IconButton(tooltip: 'Remove product', icon: const Icon(Icons.delete_outline),
                  onPressed: () => cart.setQuantity(p.id, 0)),
              ]))),
            if (selected.isNotEmpty) ...[
              const SizedBox(height: 14),
              Card(child: Padding(padding: const EdgeInsets.all(16), child: Column(children: [
                TotalRow('Subtotal (sample)', formatRm(subtotal)),
                const SizedBox(height: 8),
                const TotalRow('Delivery (sample)', 'RM 8.00'),
                const Divider(height: 24),
                TotalRow('Demo total', formatRm(subtotal + 800), strong: true),
              ]))),
              const SizedBox(height: 15),
              FilledButton.icon(onPressed: () => Navigator.of(context).push(
                MaterialPageRoute<void>(builder: (context) => CheckoutPage(
                  cart: cart, products: selected, orders: orders, checkout: checkout))),
                icon: const Icon(Icons.lock_outline), label: const Text('Checkout in app (demo)')),
            ],
          ]);
        },
      ),
    )),
  );
}

