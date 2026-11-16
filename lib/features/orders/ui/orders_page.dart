import 'package:flutter/material.dart';
import '../../../core/legacy_palette.dart';
import '../../../core/money.dart';
import '../../../core/widgets/section_title.dart';
import '../state/orders_store.dart';
import 'order_detail_page.dart';
import 'order_status.dart';

class OrdersPage extends StatefulWidget {
  const OrdersPage({super.key, required this.orders});
  final OrdersStore orders;
  @override
  State<OrdersPage> createState() => _OrdersPageState();
}

class _OrdersPageState extends State<OrdersPage> {
  int revision = 0;
  @override
  Widget build(BuildContext context) => AnimatedBuilder(animation: widget.orders, builder: (context, _) => bounded(
    ListView(padding: const EdgeInsets.all(18), children: [
      Row(children: [const Expanded(child: SectionTitle('My orders')),
        IconButton(tooltip: 'Refresh tracking', icon: const Icon(Icons.refresh),
          onPressed: () => setState(() => revision++))]),
      const SizedBox(height: 6),
      const Text('Independent demo orders only. Not official Sagemaker orders.',
        style: TextStyle(color: Colors.black54)),
      const SizedBox(height: 18),
      if (widget.orders.saved.isEmpty) const Card(child: Padding(
        padding: EdgeInsets.all(25), child: Column(children: [
          Icon(Icons.receipt_long_outlined, size: 45, color: forest),
          SizedBox(height: 10), Text('No orders yet. Try the in-app demo checkout.'),
        ]))),
      for (final saved in widget.orders.saved)
        FutureBuilder<Map<String, dynamic>>(
          key: ValueKey('${saved.id}-$revision'), future: widget.orders.getOrder(saved),
          builder: (context, snapshot) => Card(child: ListTile(
            title: Text(saved.id, style: const TextStyle(fontWeight: FontWeight.w800, color: deep)),
            subtitle: Text(snapshot.hasData ? '${prettyStatus(snapshot.data!['status'] as String)} • ${formatRm(snapshot.data!['totalSen'] as int)} demo'
              : snapshot.hasError ? 'Cannot load from Python backend' : 'Loading status...'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(
              builder: (context) => OrderDetailPage(saved: saved, orders: widget.orders))),
          )),
        ),
    ]),
  ));
}

