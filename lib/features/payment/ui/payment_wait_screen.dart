import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../app/theme.dart';
import '../../../core/money.dart';
import '../../../core/widgets/ui_kit.dart';
import '../../checkout/data/checkout_repository.dart';
import '../../checkout/state/checkout_flow.dart';
import '../data/payment_gateway.dart';

/// Shown while the customer pays on the hosted gateway page in the browser.
/// Polls the server, which confirms the payment with the gateway, then moves on
/// to the order confirmation.
class PaymentWaitScreen extends ConsumerStatefulWidget {
  const PaymentWaitScreen({
    super.key,
    required this.paymentId,
    this.checkoutUrl,
    this.pollInterval = const Duration(seconds: 3),
    this.autoOpen = true,
  });

  final String paymentId;

  /// The hosted payment page. Opened automatically; the button opens it again.
  final String? checkoutUrl;
  final Duration pollInterval;

  /// Browsers may block a page opened outside a tap, so the button is always there.
  final bool autoOpen;

  @override
  ConsumerState<PaymentWaitScreen> createState() => _PaymentWaitScreenState();
}

class _PaymentWaitScreenState extends ConsumerState<PaymentWaitScreen>
    with WidgetsBindingObserver {
  Timer? _timer;
  GatewayPayment? _payment;
  bool _busy = false;
  bool _checkFailed = false;

  bool get _done => _payment != null && !_payment!.isPending;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _timer = Timer.periodic(widget.pollInterval, (_) => _check());
    if (widget.autoOpen) _open();
  }

  @override
  void dispose() {
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Back from the browser: check straight away instead of waiting for the timer.
    if (state == AppLifecycleState.resumed) _check();
  }

  Future<void> _open() async {
    final url = widget.checkoutUrl;
    if (url == null) return;
    try {
      await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    } catch (_) {
      // The button on screen opens it again.
    }
  }

  void _apply(GatewayPayment p) {
    if (!mounted) return;
    setState(() {
      _payment = p;
      _checkFailed = false;
    });
    if (p.isPending) return;
    _timer?.cancel();
    if (p.isPaid) {
      ref.invalidate(checkoutCartProvider);
      context.go('/confirmation/${p.orderId}');
    }
  }

  Future<void> _check() async {
    if (_busy || _done || !mounted) return;
    _busy = true;
    try {
      _apply(await ref
          .read(paymentGatewayRepositoryProvider)
          .status(widget.paymentId));
    } catch (_) {
      if (mounted) setState(() => _checkFailed = true);
    } finally {
      _busy = false;
    }
  }

  Future<void> _cancel() async {
    if (_busy) return;
    _busy = true;
    try {
      _apply(await ref
          .read(paymentGatewayRepositoryProvider)
          .cancel(widget.paymentId));
    } catch (_) {
      if (mounted) setState(() => _checkFailed = true);
    } finally {
      _busy = false;
    }
  }

  void _backToCheckout() {
    // The finished attempt is closed, so the next try needs a new payment.
    ref.read(checkoutFlowProvider.notifier).resetAttempt();
    if (context.canPop()) {
      context.pop();
    } else {
      context.go('/checkout');
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = _payment;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Complete your payment'),
        automaticallyImplyLeading: false,
      ),
      body: ListView(padding: const EdgeInsets.all(20), children: [
        if (p != null && !p.isPending)
          _Result(payment: p, onBack: _backToCheckout)
        else
          _Waiting(
            amountSen: p?.amountSen,
            checkFailed: _checkFailed,
            onOpen: widget.checkoutUrl == null ? null : _open,
            onCheck: _check,
            onCancel: _cancel,
          ),
      ]),
    );
  }
}

class _Waiting extends StatelessWidget {
  const _Waiting({
    required this.amountSen,
    required this.checkFailed,
    required this.onOpen,
    required this.onCheck,
    required this.onCancel,
  });

  final int? amountSen;
  final bool checkFailed;
  final VoidCallback? onOpen;
  final VoidCallback onCheck;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      GradientPanel(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Row(children: [
            SizedBox(
                width: 22,
                height: 22,
                child:
                    CircularProgressIndicator(strokeWidth: 3, color: kAccent)),
            SizedBox(width: 12),
            Text('Waiting for your payment',
                style: TextStyle(
                    color: Colors.white70, fontWeight: FontWeight.w600)),
          ]),
          if (amountSen != null) ...[
            const SizedBox(height: 12),
            Text(formatRm(amountSen!),
                style: const TextStyle(
                    fontFamily: kDisplayFont,
                    color: Colors.white,
                    fontSize: 34,
                    fontWeight: FontWeight.w700)),
          ],
        ]),
      ),
      const SizedBox(height: 20),
      Text('Finish paying on the secure payment page',
          style: theme.textTheme.titleMedium),
      const SizedBox(height: 6),
      Text(
          'It opened in your browser. When you are done, come back here and this '
          'page confirms your order by itself.',
          style: theme.textTheme.bodyMedium?.copyWith(color: kMuted)),
      if (checkFailed) ...[
        const SizedBox(height: 10),
        const Text('Could not check yet. Trying again...',
            key: Key('wait-check-failed'), style: TextStyle(color: kMuted)),
      ],
      const SizedBox(height: 22),
      FilledButton.icon(
        key: const Key('wait-open'),
        onPressed: onOpen,
        icon: const Icon(Icons.open_in_new),
        label: const Text('Open secure payment page'),
      ),
      const SizedBox(height: 10),
      OutlinedButton(
        key: const Key('wait-check'),
        onPressed: onCheck,
        child: const Text("I've paid, check now"),
      ),
      const SizedBox(height: 6),
      TextButton(
        key: const Key('wait-cancel'),
        onPressed: onCancel,
        child: const Text('Cancel payment'),
      ),
    ]);
  }
}

class _Result extends StatelessWidget {
  const _Result({required this.payment, required this.onBack});
  final GatewayPayment payment;
  final VoidCallback onBack;

  (String, IconData, Color) get _look => switch (payment.status) {
        'cancelled' => ('Payment cancelled', Icons.close_rounded, kMuted),
        'expired' => ('Payment expired', Icons.timer_off_outlined, kMuted),
        'refunded' => (
            'Payment refunded',
            Icons.undo_rounded,
            const Color(0xFFB7791F)
          ),
        _ => ('Payment problem', Icons.priority_high_rounded, kError),
      };

  @override
  Widget build(BuildContext context) {
    final (title, icon, color) = _look;
    final theme = Theme.of(context);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const SizedBox(height: 24),
      Center(
        child: Container(
          width: 96,
          height: 96,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          child: Icon(icon, color: Colors.white, size: 52),
        ),
      ),
      const SizedBox(height: 18),
      Text(title,
          key: const Key('wait-result-title'),
          textAlign: TextAlign.center,
          style: theme.textTheme.headlineMedium),
      const SizedBox(height: 8),
      Text(payment.message ?? 'No money was taken. You can try again.',
          key: const Key('wait-result-message'),
          textAlign: TextAlign.center,
          style: theme.textTheme.bodyMedium?.copyWith(color: kMuted)),
      const SizedBox(height: 24),
      FilledButton(
        key: const Key('wait-back'),
        onPressed: onBack,
        child: const Text('Back to checkout'),
      ),
    ]);
  }
}
