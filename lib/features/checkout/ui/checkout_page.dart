import 'dart:math';

import 'package:flutter/material.dart';
import '../../../core/widgets/section_title.dart';
import '../../catalogue/data/product.dart';
import '../../../core/network/app_failure.dart';
import '../../../core/storage/legacy_local_store.dart';
import '../../cart/state/cart_store.dart';
import '../../orders/state/orders_store.dart';
import '../../orders/ui/order_detail_page.dart';
import '../data/legacy_checkout_repository.dart';

class CheckoutPage extends StatefulWidget {
  const CheckoutPage({super.key, required this.cart, required this.products, required this.orders, required this.checkout});
  final CartStore cart;
  final List<Product> products;
  final OrdersStore orders;
  final LegacyCheckoutRepository checkout;
  @override
  State<CheckoutPage> createState() => _CheckoutPageState();
}

class _CheckoutPageState extends State<CheckoutPage> {
  final formKey = GlobalKey<FormState>();
  final name = TextEditingController();
  final email = TextEditingController();
  final phone = TextEditingController();
  final address = TextEditingController();
  final checkoutId = 'check_${DateTime.now().microsecondsSinceEpoch}_${Random().nextInt(0x7fffffff)}';
  String paymentMethod = 'demo_card';
  bool submitting = false;
  String? error;

  @override
  void dispose() {
    name.dispose(); email.dispose(); phone.dispose(); address.dispose(); super.dispose();
  }

  Widget field(TextEditingController controller, String label, {int lines = 1,
      TextInputType? keyboard}) => Padding(padding: const EdgeInsets.only(bottom: 12), child: TextFormField(
    controller: controller,
    maxLines: lines,
    keyboardType: keyboard,
    decoration: InputDecoration(labelText: label, filled: true, fillColor: Colors.white,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12))),
    validator: (v) => (v?.trim().length ?? 0) < (lines > 1 ? 10 : 2) ? 'Please enter $label' : null,
  ));

  Future<void> submit() async {
    if (submitting || !formKey.currentState!.validate()) return;
    setState(() { submitting = true; error = null; });
    try {
      final result = await widget.checkout.placeOrder({
        'checkout_id': checkoutId,
        'customer_name': name.text.trim(),
        'email': email.text.trim(),
        'phone': phone.text.trim(),
        'delivery_address': address.text.trim(),
        'payment_method': paymentMethod,
        'items': widget.products.map((p) => {
          'product_id': p.id, 'quantity': widget.cart.quantity(p.id),
        }).toList(),
      });
      final saved = SavedOrder(result['id'] as String, result['accessToken'] as String);
      await widget.orders.add(saved);
      await widget.cart.clear();
      if (!mounted) return;
      Navigator.of(context).pushReplacement(MaterialPageRoute<void>(
        builder: (context) => OrderDetailPage(saved: saved, orders: widget.orders)));
    } on AppFailure catch (e) {
      if (mounted) setState(() => error = 'Checkout failed: ${e.message}');
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Checkout')),
    body: bounded(ListView(padding: const EdgeInsets.all(18), children: [
      const SectionTitle('Delivery details'),
      const SizedBox(height: 8),
      const Card(child: Padding(padding: EdgeInsets.all(14), child: Row(children: [
        Icon(Icons.warning_amber, color: Color(0xFF9A5900)), SizedBox(width: 12),
        Expanded(child: Text('DEMO ONLY — no real money is charged and nothing is delivered. Use fictional details.',
          style: TextStyle(fontWeight: FontWeight.w700))),
      ]))),
      const SizedBox(height: 15),
      Form(key: formKey, child: Column(children: [
        field(name, 'Full name'),
        field(email, 'Email', keyboard: TextInputType.emailAddress),
        field(phone, 'Phone', keyboard: TextInputType.phone),
        field(address, 'Delivery address', lines: 3),
      ])),
      const SizedBox(height: 16),
      const SectionTitle('Payment method (simulation)'),
      RadioGroup<String>(
        groupValue: paymentMethod,
        onChanged: (v) => setState(() => paymentMethod = v ?? paymentMethod),
        child: const Column(children: [
          RadioListTile<String>(title: Text('Demo credit/debit card'), value: 'demo_card'),
          RadioListTile<String>(title: Text('Demo FPX online banking'), value: 'demo_fpx'),
          RadioListTile<String>(title: Text('Demo eWallet'), value: 'demo_ewallet'),
        ]),
      ),
      const Text('Do not enter card numbers or banking passwords. Payment is simulated on our local Python API.',
        style: TextStyle(color: Colors.black54, fontSize: 12)),
      const SizedBox(height: 16),
      if (error != null) Text(error!, style: const TextStyle(color: Colors.red)),
      FilledButton.icon(onPressed: submitting ? null : submit,
        icon: submitting ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
          : const Icon(Icons.check_circle_outline),
        label: Text(submitting ? 'Creating demo order...' : 'Place demo order (no charge)')),
    ])),
  );
}

