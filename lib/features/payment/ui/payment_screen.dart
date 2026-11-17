import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme.dart';
import '../../../core/money.dart';
import '../../../core/network/app_failure.dart';
import '../../../core/widgets/back_fallback.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../../core/widgets/ui_kit.dart';
import '../../checkout/data/checkout_models.dart';
import '../../checkout/data/checkout_repository.dart';
import '../../checkout/state/checkout_flow.dart' show couldNotProcessMessage;
import '../data/malaysia_payments.dart';
import '../data/payment_gateway.dart';
import 'payment_chooser.dart';
import 'payment_gateway_screen.dart';

/// Retry payment for an order in `payment_failed` (Req 13.11, 13.12, 13.13).
class PaymentScreen extends ConsumerStatefulWidget {
  const PaymentScreen({super.key, required this.orderId});
  final String orderId;

  @override
  ConsumerState<PaymentScreen> createState() => _PaymentScreenState();
}

class _PaymentScreenState extends ConsumerState<PaymentScreen> {
  PaymentChannel? _channel;
  String? _providerId;
  bool _busy = false;
  String? _error;
  List<StockShortage> _shortages = const [];

  bool get _ready =>
      _channel != null && (!_channel!.needsProvider || _providerId != null);

  Future<void> _submit(int amountSen) async {
    if (_busy || !_ready) return;
    String? outcome;
    if (_channel != PaymentChannel.cod) {
      outcome = await openPaymentGateway(context,
          channel: _channel!, providerId: _providerId, amountSen: amountSen);
      if (outcome == null || !mounted) return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _shortages = const [];
    });
    try {
      await ref.read(checkoutRepositoryProvider).retryPayment(
          widget.orderId, _channel!.method, outcome,
          provider: _channel!.providerFor(_providerId));
      ref.invalidate(placedOrderProvider(widget.orderId));
      if (mounted) context.go('/confirmation/${widget.orderId}');
    } on ConflictFailure catch (e) {
      final shortages = [
        for (final d in e.details)
          if (d is Map) StockShortage.fromJson(Map<String, dynamic>.from(d)),
      ];
      if (!mounted) return;
      setState(() {
        _busy = false;
        _shortages = shortages;
        _error = shortages.isEmpty
            ? e.message
            : 'Some items are out of stock. The order stays unpaid.';
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = couldNotProcessMessage;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final order = ref.watch(placedOrderProvider(widget.orderId));
    final config = ref.watch(paymentConfigProvider).value;
    return Scaffold(
      appBar: AppBar(
          leading: const FallbackBackButton(fallback: '/orders'),
          title: const Text('Payment')),
      body: order.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(
            message: 'Could not load this order',
            onRetry: () => ref.invalidate(placedOrderProvider(widget.orderId))),
        data: (o) {
          if (!o.canRetryPayment) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  const Text('This order does not need a new payment.'),
                  const SizedBox(height: 12),
                  FilledButton(
                      onPressed: () =>
                          context.go('/confirmation/${widget.orderId}'),
                      child: const Text('View result')),
                ]),
              ),
            );
          }
          return ListView(padding: const EdgeInsets.all(16), children: [
            GradientPanel(
              child: Row(children: [
                Expanded(
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Order ${o.id}',
                            style: const TextStyle(color: Colors.white70)),
                        const SizedBox(height: 4),
                        Text(formatRm(o.totalSen),
                            style: const TextStyle(
                                fontFamily: kDisplayFont,
                                color: Colors.white,
                                fontSize: 30,
                                fontWeight: FontWeight.w700)),
                      ]),
                ),
                const Icon(Icons.replay_circle_filled,
                    color: kAccent, size: 40),
              ]),
            ),
            const SizedBox(height: 20),
            PaymentChooser(
              channel: _channel,
              providerId: _providerId,
              amountSen: o.totalSen,
              config: config,
              // With the real gateway a failed order cannot be re-paid with a
              // simulated payment; place it again from the cart instead.
              codOnly: config?.isHosted ?? false,
              onChanged: (c, p) => setState(() {
                _channel = c;
                _providerId = p;
              }),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!,
                  key: const Key('paymentError'),
                  style: const TextStyle(color: kError)),
              for (final s in _shortages) Text(s.text),
            ],
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _ready && !_busy ? () => _submit(o.totalSen) : null,
              child: Text(_busy
                  ? 'Processing...'
                  : _channel == PaymentChannel.cod
                      ? 'Confirm cash on delivery'
                      : 'Pay ${formatRm(o.totalSen)}'),
            ),
          ]);
        },
      ),
    );
  }
}
