import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/money.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../data/order_models.dart';
import '../state/my_orders_provider.dart';
import 'my_orders_screen.dart' show orderLoadErrorMessage;

/// Order detail with the status timeline (Req 15.3, 15.6 to 15.10).
class OrderTrackingScreen extends ConsumerWidget {
  const OrderTrackingScreen({super.key, required this.orderId});
  final String orderId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(orderDetailProvider(orderId));
    final notifier = ref.read(orderDetailProvider(orderId).notifier);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Order tracking'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: notifier.refresh,
          ),
        ],
      ),
      body: value.hasValue
          ? Column(children: [
              if (value.requireValue.refreshFailed)
                MaterialBanner(
                  content: const Text(
                      'Refresh failed. Showing the last loaded status.'),
                  actions: [
                    TextButton(
                        onPressed: notifier.refresh, child: const Text('Retry')),
                  ],
                ),
              Expanded(
                child: RefreshIndicator(
                  onRefresh: notifier.refresh,
                  child: _OrderBody(order: value.requireValue.order),
                ),
              ),
            ])
          : value.hasError
              ? ErrorView(
                  message: orderLoadErrorMessage(value.error!),
                  onRetry: notifier.retry)
              : const LoadingView(),
    );
  }
}

class _OrderBody extends StatelessWidget {
  const _OrderBody({required this.order});
  final OrderDetail order;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final d = order.delivery;
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(16),
      children: [
        Row(children: [
          Expanded(child: Text(order.id, style: textTheme.titleMedium)),
        ]),
        const SizedBox(height: 4),
        Text('Status: ${orderStatusLabel(order.status)}',
            key: const ValueKey('order-status')),
        const SizedBox(height: 16),
        Text('Tracking', style: textTheme.titleSmall),
        _Timeline(steps: buildTimeline(order.status, order.history)),
        const SizedBox(height: 8),
        ListTile(
          key: const ValueKey('shipping-reference'),
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.local_shipping_outlined),
          title: const Text('Shipping reference'),
          subtitle: Text(order.shippingReference ?? 'Not available yet'),
        ),
        if (order.productionLabel != null)
          Card(
            key: const ValueKey('production-label'),
            child: ListTile(
              leading: const Icon(Icons.handyman_outlined),
              title: const Text('Production'),
              subtitle: Text(order.productionLabel!),
            ),
          ),
        const Divider(),
        Text('Items', style: textTheme.titleSmall),
        for (final l in order.lines)
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(l.name),
            subtitle: Text(
                '${l.variationLabel == null ? '' : '${l.variationLabel} · '}'
                'Qty ${l.quantity} × ${formatRm(l.unitPriceSen)}'),
            trailing: Text(formatRm(l.lineTotalSen)),
          ),
        const Divider(),
        _row('Subtotal', formatRm(order.subtotalSen)),
        _row('Delivery', formatRm(order.shippingFeeSen)),
        _row('Total', formatRm(order.totalSen), strong: true),
        const Divider(),
        Text('Delivery details', style: textTheme.titleSmall),
        Text(d.name),
        Text(d.phone),
        Text(d.email),
        Text([d.address, d.postcode, d.state]
            .whereType<String>()
            .where((e) => e.isNotEmpty)
            .join(', ')),
        if (d.notes != null) Text('Notes: ${d.notes}'),
        const Divider(),
        _row('Payment method',
            paymentWithProvider(order.paymentMethod, order.paymentProvider)),
        _row('Payment status', paymentStatusLabel(order.paymentStatus)),
      ],
    );
  }

  Widget _row(String label, String value, {bool strong = false}) {
    final style = strong ? const TextStyle(fontWeight: FontWeight.w700) : null;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [Text(label, style: style), Text(value, style: style)],
      ),
    );
  }
}

class _Timeline extends StatelessWidget {
  const _Timeline({required this.steps});
  final List<TimelineStep> steps;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      children: [
        for (final s in steps)
          ListTile(
            key: ValueKey('step-${s.status}'),
            contentPadding: EdgeInsets.zero,
            dense: true,
            leading: Icon(
              s.terminal
                  ? Icons.cancel
                  : s.reached
                      ? Icons.check_circle
                      : Icons.radio_button_unchecked,
              color: s.terminal
                  ? scheme.error
                  : s.reached
                      ? scheme.primary
                      : scheme.outline,
              semanticLabel: s.terminal
                  ? 'Ended'
                  : s.reached
                      ? 'Reached'
                      : 'Not yet reached',
            ),
            title: Text(s.label),
            subtitle: Text(s.reached
                ? (s.at == null ? 'Reached' : formatLocalDateTime(s.at!))
                : 'Not yet reached'),
          ),
      ],
    );
  }
}
