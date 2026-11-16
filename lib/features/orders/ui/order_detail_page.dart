import 'package:flutter/material.dart';
import '../../../core/legacy_palette.dart';
import '../../../core/money.dart';
import '../../../core/widgets/section_title.dart';
import '../../../core/widgets/total_row.dart';
import '../../../core/storage/legacy_local_store.dart';
import '../state/orders_store.dart';
import 'order_status.dart';

class OrderDetailPage extends StatefulWidget {
  const OrderDetailPage({super.key, required this.saved, required this.orders});
  final SavedOrder saved;
  final OrdersStore orders;
  @override
  State<OrderDetailPage> createState() => _OrderDetailPageState();
}

class _OrderDetailPageState extends State<OrderDetailPage> {
  late Future<Map<String, dynamic>> order;
  @override
  void initState() {
    super.initState();
    order = widget.orders.getOrder(widget.saved);
  }

  void refresh() =>
      setState(() => order = widget.orders.getOrder(widget.saved));
  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Order tracking'), actions: [
          IconButton(
              onPressed: refresh,
              icon: const Icon(Icons.refresh),
              tooltip: 'Refresh')
        ]),
        body: bounded(FutureBuilder<Map<String, dynamic>>(
          future: order,
          builder: (context, snapshot) {
            if (!snapshot.hasData) {
              return Center(
                  child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Text(snapshot.hasError
                          ? 'Cannot load order. Check the Python API and tap refresh.'
                          : 'Loading order...')));
            }
            final info = snapshot.data!;
            final status = info['status'] as String;
            final stepIndex = trackingSteps.indexOf(status);
            final products = info['items'] as List<dynamic>;
            return ListView(padding: const EdgeInsets.all(18), children: [
              const SectionTitle('Your demo order'),
              const SizedBox(height: 6),
              Text(widget.saved.id,
                  style: const TextStyle(
                      fontWeight: FontWeight.w800, color: forest)),
              const SizedBox(height: 12),
              const Card(
                  child: Padding(
                      padding: EdgeInsets.all(14),
                      child: Text(
                          'DEMO TRACKING: Updated manually by the demo store admin. No parcel was purchased or shipped.',
                          style: TextStyle(
                              color: Color(0xFF7E5500),
                              fontWeight: FontWeight.w700)))),
              const SizedBox(height: 20),
              const SectionTitle('Delivery progress'),
              const SizedBox(height: 12),
              for (var i = 0; i < trackingSteps.length; i++)
                ListTile(
                  leading: Icon(
                      i <= stepIndex
                          ? Icons.check_circle
                          : Icons.radio_button_unchecked,
                      color: i <= stepIndex ? forest : Colors.grey),
                  title: Text(prettyStatus(trackingSteps[i]),
                      style: TextStyle(
                          fontWeight: i == stepIndex
                              ? FontWeight.w800
                              : FontWeight.normal)),
                  subtitle: i == stepIndex ? const Text('Current step') : null,
                ),
              if (info['trackingNumber'] != null) ...[
                const SizedBox(height: 8),
                Text('Demo tracking reference: ${info['trackingNumber']}',
                    style: const TextStyle(fontWeight: FontWeight.w700)),
              ],
              const SizedBox(height: 18),
              const SectionTitle('Items'),
              for (final raw in products)
                ListTile(
                    title: Text(raw['name'] as String),
                    subtitle: Text('Quantity: ${raw['quantity']}'),
                    trailing: Text(formatRm(raw['lineTotalSen'] as int))),
              const Divider(),
              TotalRow(
                  'Delivery (demo)', formatRm(info['shippingFeeSen'] as int)),
              const SizedBox(height: 8),
              TotalRow('Order total (demo)', formatRm(info['totalSen'] as int),
                  strong: true),
              const SizedBox(height: 12),
              const Text('Payment: simulated only, no funds were collected.',
                  style: TextStyle(color: Colors.black54, fontSize: 12)),
              const SizedBox(height: 15),
              OutlinedButton.icon(
                  onPressed: refresh,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Refresh order status')),
            ]);
          },
        )),
      );
}
