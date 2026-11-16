import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme.dart';
import '../../../core/money.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../../core/widgets/ui_kit.dart';
import '../../checkout/data/checkout_models.dart';
import '../../checkout/data/checkout_repository.dart';

/// Title and message matching the payment outcome (Req 13.10).
({String title, String message, IconData icon}) confirmationCopy(
    PlacedOrder o) {
  switch (o.paymentStatus) {
    case 'paid':
      return (
        title: 'Payment successful',
        message:
            'Thank you! Your order is confirmed and our artisans will start preparing it.',
        icon: Icons.check_rounded,
      );
    case 'pending_cod':
      return (
        title: 'Order placed',
        message: 'Pay cash on delivery. The payment is recorded as pending.',
        icon: Icons.local_shipping_outlined,
      );
    case 'cancelled':
      return (
        title: 'Payment cancelled',
        message: 'The payment was cancelled and the order is cancelled.',
        icon: Icons.close_rounded,
      );
    default:
      return (
        title: 'Payment failed',
        message: 'The payment failed. You can retry the payment.',
        icon: Icons.priority_high_rounded,
      );
  }
}

Color _statusColor(String paymentStatus) => switch (paymentStatus) {
      'paid' => kSuccess,
      'pending_cod' => kPrimaryLight,
      'cancelled' => kMuted,
      _ => kError,
    };

/// Result screen after checkout or a payment retry (Req 13.10).
class ConfirmationScreen extends ConsumerWidget {
  const ConfirmationScreen({super.key, required this.orderId});
  final String orderId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final order = ref.watch(placedOrderProvider(orderId));
    return Scaffold(
      appBar: AppBar(title: const Text('Order confirmation')),
      body: order.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(
            message: 'Could not load this order',
            onRetry: () => ref.invalidate(placedOrderProvider(orderId))),
        data: (o) {
          final copy = confirmationCopy(o);
          final color = _statusColor(o.paymentStatus);
          final theme = Theme.of(context);
          return ListView(padding: const EdgeInsets.all(20), children: [
            const SizedBox(height: 8),
            Center(
                child: _ResultBadge(
                    icon: copy.icon, color: color, label: copy.title)),
            const SizedBox(height: 18),
            FadeSlideIn(
              index: 2,
              child: Text(copy.title,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.headlineMedium),
            ),
            const SizedBox(height: 6),
            FadeSlideIn(
              index: 3,
              child: Text(copy.message,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyMedium?.copyWith(color: kMuted)),
            ),
            const SizedBox(height: 22),
            FadeSlideIn(
              index: 4,
              child: SoftCard(
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(children: [
                        const Icon(Icons.receipt_long_outlined,
                            color: kPrimary),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text('Order ${o.id}',
                              style: theme.textTheme.titleMedium),
                        ),
                        StatusPill(paymentMethodLabel(o.paymentMethod),
                            color: color),
                      ]),
                      const Divider(),
                      for (final l in o.lines)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 3),
                          child: Row(children: [
                            Expanded(
                              child: Text(
                                  '${l.quantity} x ${l.name}${l.variationLabel == null ? '' : ' (${l.variationLabel})'}'),
                            ),
                            Text(formatRm(l.lineTotalSen)),
                          ]),
                        ),
                      const Divider(),
                      Row(children: [
                        Text('Total', style: theme.textTheme.titleMedium),
                        const Spacer(),
                        Text(formatRm(o.totalSen),
                            style: theme.textTheme.titleMedium),
                      ]),
                    ]),
              ),
            ),
            const SizedBox(height: 24),
            if (o.canRetryPayment)
              FilledButton(
                  onPressed: () => context.go('/payment/${o.id}'),
                  child: const Text('Retry payment')),
            if (o.canRetryPayment) const SizedBox(height: 8),
            if (o.paymentStatus == 'paid' || o.paymentStatus == 'pending_cod')
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: FilledButton.icon(
                    onPressed: () => context.go('/orders/${o.id}'),
                    icon: const Icon(Icons.local_shipping_outlined),
                    label: const Text('Track order')),
              ),
            OutlinedButton(
                onPressed: () => context.go('/shop'),
                child: const Text('Return to shop')),
          ]);
        },
      ),
    );
  }
}

/// Circle that pops in with an elastic scale.
class _ResultBadge extends StatelessWidget {
  const _ResultBadge(
      {required this.icon, required this.color, required this.label});
  final IconData icon;
  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
        tween: Tween(begin: 0, end: 1),
        duration: const Duration(milliseconds: 750),
        curve: Curves.elasticOut,
        builder: (_, t, child) => Transform.scale(scale: t, child: child),
        child: Container(
          width: 112,
          height: 112,
          decoration: BoxDecoration(
            color: color,
            shape: BoxShape.circle,
            boxShadow: [
              BoxShadow(
                  color: color.withValues(alpha: 0.35),
                  blurRadius: 30,
                  spreadRadius: 4),
            ],
          ),
          child:
              Icon(icon, size: 60, color: Colors.white, semanticLabel: label),
        ),
      );
}
