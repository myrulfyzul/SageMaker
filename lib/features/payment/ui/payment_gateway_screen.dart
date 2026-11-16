import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../../../app/theme.dart';
import '../../../core/money.dart';
import '../data/malaysia_payments.dart';
import 'payment_chooser.dart';

/// Opens the prototype payment gateway for [channel]. Resolves to `success`,
/// `failed` or `cancelled`, or null when the shopper closes it without
/// deciding (no order is created then). Nothing typed here leaves the device.
Future<String?> openPaymentGateway(
  BuildContext context, {
  required PaymentChannel channel,
  required String? providerId,
  required int amountSen,
}) {
  return Navigator.of(context, rootNavigator: true).push<String>(
    PageRouteBuilder(
      fullscreenDialog: true,
      transitionDuration: const Duration(milliseconds: 380),
      pageBuilder: (_, __, ___) => PaymentGatewayScreen(
          channel: channel, providerId: providerId, amountSen: amountSen),
      transitionsBuilder: (_, a, __, child) => SlideTransition(
        position: Tween(begin: const Offset(0, 1), end: Offset.zero)
            .animate(CurvedAnimation(parent: a, curve: Curves.easeOutCubic)),
        child: child,
      ),
    ),
  );
}

class PaymentGatewayScreen extends StatefulWidget {
  const PaymentGatewayScreen({
    super.key,
    required this.channel,
    required this.providerId,
    required this.amountSen,
  });
  final PaymentChannel channel;
  final String? providerId;
  final int amountSen;

  @override
  State<PaymentGatewayScreen> createState() => _PaymentGatewayScreenState();
}

class _PaymentGatewayScreenState extends State<PaymentGatewayScreen> {
  bool _processing = false;
  String? _result;
  late final String _reference =
      'SGM${DateTime.now().millisecondsSinceEpoch.toString().substring(5)}';

  PaymentProvider get _provider => switch (widget.channel) {
        PaymentChannel.duitnow => duitNowProvider,
        PaymentChannel.card => cardProvider,
        _ => providerById(widget.providerId) ?? cardProvider,
      };

  /// Shows the processing animation, then returns [outcome] to checkout.
  Future<void> _finish(String outcome) async {
    if (_processing) return;
    HapticFeedback.mediumImpact();
    setState(() => _processing = true);
    await Future.delayed(const Duration(milliseconds: 1400));
    if (!mounted) return;
    setState(() => _result = outcome);
    await Future.delayed(const Duration(milliseconds: 1100));
    if (mounted) Navigator.of(context).pop(outcome);
  }

  Future<void> _confirmCancel() async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Cancel this payment?'),
        content: const Text(
            'Your order will be recorded as cancelled and no money is taken.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(c, false),
              child: const Text('Keep paying')),
          FilledButton(
              onPressed: () => Navigator.pop(c, true),
              child: const Text('Cancel payment')),
        ],
      ),
    );
    if (yes == true) _finish('cancelled');
  }

  @override
  Widget build(BuildContext context) {
    final p = _provider;
    final body = switch (widget.channel) {
      PaymentChannel.fpx => _FpxFlow(bank: p, onDone: _finish),
      PaymentChannel.ewallet => _WalletFlow(wallet: p, onDone: _finish),
      PaymentChannel.duitnow => _DuitNowFlow(
          reference: _reference, amountSen: widget.amountSen, onDone: _finish),
      _ => _CardFlow(amountSen: widget.amountSen, onDone: _finish),
    };
    return PopScope(
      canPop: !_processing,
      child: Scaffold(
        backgroundColor: kBackground,
        appBar: AppBar(
          leading: IconButton(
            tooltip: 'Close',
            icon: const Icon(Icons.close),
            onPressed: _processing ? null : () => Navigator.of(context).pop(),
          ),
          title: Row(children: [
            ProviderBadge(provider: p, size: 30),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                  widget.channel == PaymentChannel.card
                      ? 'Card payment'
                      : p.name,
                  overflow: TextOverflow.ellipsis),
            ),
          ]),
          actions: [
            Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Row(children: const [
                Icon(Icons.lock, size: 16, color: kSuccess),
                SizedBox(width: 4),
                Text('Secure',
                    style: TextStyle(
                        color: kSuccess, fontWeight: FontWeight.w700)),
              ]),
            ),
          ],
        ),
        body: Stack(children: [
          ListView(
            padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
            children: [
              _AmountCard(
                  amountSen: widget.amountSen,
                  reference: _reference,
                  channel: widget.channel),
              const SizedBox(height: 20),
              body,
              const SizedBox(height: 16),
              if (!_processing)
                Center(
                  child: TextButton.icon(
                    key: const Key('gateway-cancel'),
                    onPressed: _confirmCancel,
                    icon: const Icon(Icons.block, size: 18),
                    label: const Text('Cancel payment'),
                  ),
                ),
              const SizedBox(height: 8),
              const _PrototypeFooter(),
            ],
          ),
          if (_processing) _ProcessingOverlay(result: _result),
        ]),
      ),
    );
  }
}

class _AmountCard extends StatelessWidget {
  const _AmountCard(
      {required this.amountSen,
      required this.reference,
      required this.channel});
  final int amountSen;
  final String reference;
  final PaymentChannel channel;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: kHeroGradient,
        borderRadius: BorderRadius.circular(24),
        boxShadow: softShadow(0.18),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Paying to',
            style: TextStyle(color: Colors.white70, fontSize: 12)),
        const Text('SageMaker Asia',
            style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w700)),
        const SizedBox(height: 14),
        Text(formatRm(amountSen),
            style: const TextStyle(
                fontFamily: kDisplayFont,
                color: Colors.white,
                fontSize: 36,
                fontWeight: FontWeight.w700)),
        const SizedBox(height: 10),
        Row(children: [
          _chip(Icons.tag, reference),
          const SizedBox(width: 8),
          _chip(channel.icon, channel.label),
        ]),
      ]),
    );
  }

  Widget _chip(IconData icon, String text) => Flexible(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.14),
              borderRadius: BorderRadius.circular(999)),
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, size: 14, color: kAccent),
            const SizedBox(width: 6),
            Flexible(
              child: Text(text,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white, fontSize: 12)),
            ),
          ]),
        ),
      );
}

class _PrototypeFooter extends StatelessWidget {
  const _PrototypeFooter();

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color(0xFFF3EEE4),
          borderRadius: BorderRadius.circular(14),
        ),
        child: const Row(children: [
          Icon(Icons.science_outlined, size: 18, color: kMuted),
          SizedBox(width: 8),
          Expanded(
            child: Text(
              'Prototype gateway: no real money moves and nothing you type is sent. '
              'Enter $declineTestCode as the code to try a declined payment.',
              style: TextStyle(fontSize: 12, color: kMuted, height: 1.4),
            ),
          ),
        ]),
      );
}

class _ProcessingOverlay extends StatelessWidget {
  const _ProcessingOverlay({required this.result});
  final String? result;

  @override
  Widget build(BuildContext context) {
    final (icon, color, text) = switch (result) {
      null => (null, kPrimary, 'Processing your payment...'),
      'success' => (Icons.check_rounded, kSuccess, 'Payment approved'),
      'cancelled' => (Icons.close_rounded, kMuted, 'Payment cancelled'),
      _ => (Icons.priority_high_rounded, kError, 'Payment declined'),
    };
    return Positioned.fill(
      child: ColoredBox(
        color: kBackground.withValues(alpha: 0.94),
        child: Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 350),
              transitionBuilder: (c, a) =>
                  ScaleTransition(scale: a, child: c),
              child: icon == null
                  ? const SizedBox(
                      key: ValueKey('spin'),
                      width: 84,
                      height: 84,
                      child: CircularProgressIndicator(strokeWidth: 5))
                  : Container(
                      key: ValueKey(result),
                      width: 84,
                      height: 84,
                      decoration:
                          BoxDecoration(color: color, shape: BoxShape.circle),
                      child: Icon(icon, color: Colors.white, size: 48),
                    ),
            ),
            const SizedBox(height: 20),
            Text(text,
                key: const Key('gateway-status'),
                style: Theme.of(context).textTheme.titleLarge),
          ]),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// FPX: redirect, bank login, TAC.

class _FpxFlow extends StatefulWidget {
  const _FpxFlow({required this.bank, required this.onDone});
  final PaymentProvider bank;
  final ValueChanged<String> onDone;

  @override
  State<_FpxFlow> createState() => _FpxFlowState();
}

class _FpxFlowState extends State<_FpxFlow> {
  int _stage = 0; // 0 redirecting, 1 login, 2 TAC
  final _user = TextEditingController();
  final _pass = TextEditingController();
  final _tac = TextEditingController();
  bool _tacSent = false;
  String? _error;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer(const Duration(milliseconds: 1300), () {
      if (mounted) setState(() => _stage = 1);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    for (final c in [_user, _pass, _tac]) {
      c.clear();
      c.dispose();
    }
    super.dispose();
  }

  void _login() {
    if (_user.text.trim().length < 4 || _pass.text.length < 6) {
      setState(() => _error =
          'Enter your username (4+ characters) and password (6+ characters).');
      return;
    }
    _pass.clear();
    setState(() {
      _error = null;
      _stage = 2;
    });
  }

  void _approve() {
    final tac = _tac.text.trim();
    if (!_tacSent) {
      setState(() => _error = 'Request a TAC first.');
      return;
    }
    if (!RegExp(r'^\d{6}$').hasMatch(tac)) {
      setState(() => _error = 'The TAC has 6 digits.');
      return;
    }
    widget.onDone(tac == declineTestCode ? 'failed' : 'success');
  }

  @override
  Widget build(BuildContext context) {
    final b = widget.bank;
    final header = Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: b.color,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: Row(children: [
        Text(b.name,
            style: TextStyle(
                color: b.onColor, fontWeight: FontWeight.w800, fontSize: 16)),
        const Spacer(),
        Text('FPX',
            style: TextStyle(
                color: b.onColor.withValues(alpha: 0.8),
                fontWeight: FontWeight.w800)),
      ]),
    );
    final content = switch (_stage) {
      0 => Padding(
          padding: const EdgeInsets.symmetric(vertical: 40),
          child: Column(children: [
            CircularProgressIndicator(color: b.color),
            const SizedBox(height: 16),
            Text('Redirecting you securely to ${b.name}...'),
          ]),
        ),
      1 => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('Log in to ${b.name}',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          TextField(
            key: const Key('fpx-user'),
            controller: _user,
            autocorrect: false,
            enableSuggestions: false,
            decoration: const InputDecoration(
                labelText: 'Username', prefixIcon: Icon(Icons.person_outline)),
          ),
          const SizedBox(height: 10),
          TextField(
            key: const Key('fpx-pass'),
            controller: _pass,
            obscureText: true,
            autocorrect: false,
            enableSuggestions: false,
            decoration: const InputDecoration(
                labelText: 'Password', prefixIcon: Icon(Icons.lock_outline)),
            onSubmitted: (_) => _login(),
          ),
          const SizedBox(height: 14),
          FilledButton(
            key: const Key('fpx-login'),
            style: FilledButton.styleFrom(
                backgroundColor: b.color, foregroundColor: b.onColor),
            onPressed: _login,
            child: const Text('Log in'),
          ),
        ]),
      _ => Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('Authorise payment',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 6),
          const Text('From: Savings Account •••• 4821'),
          const SizedBox(height: 14),
          Row(children: [
            Expanded(
              child: TextField(
                key: const Key('fpx-tac'),
                controller: _tac,
                keyboardType: TextInputType.number,
                maxLength: 6,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly],
                decoration: const InputDecoration(
                    labelText: 'TAC', counterText: ''),
              ),
            ),
            const SizedBox(width: 10),
            OutlinedButton(
              key: const Key('fpx-request-tac'),
              onPressed: () => setState(() {
                _tacSent = true;
                _error = null;
              }),
              child: Text(_tacSent ? 'Resend' : 'Request TAC'),
            ),
          ]),
          if (_tacSent)
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text('TAC sent by SMS to +60 1•-••• 7789',
                  style: TextStyle(fontSize: 12, color: kMuted)),
            ),
          const SizedBox(height: 14),
          FilledButton(
            key: const Key('fpx-approve'),
            style: FilledButton.styleFrom(
                backgroundColor: b.color, foregroundColor: b.onColor),
            onPressed: _approve,
            child: const Text('Approve payment'),
          ),
        ]),
    };
    return Container(
      decoration: BoxDecoration(
        color: kCard,
        borderRadius: BorderRadius.circular(20),
        boxShadow: softShadow(),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        header,
        Padding(
          padding: const EdgeInsets.all(16),
          child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 300),
              child: KeyedSubtree(key: ValueKey(_stage), child: content)),
        ),
        if (_error != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: Text(_error!, style: const TextStyle(color: kError)),
          ),
      ]),
    );
  }
}

// ---------------------------------------------------------------------------
// E-wallet: 6-digit PIN pad.

class _WalletFlow extends StatefulWidget {
  const _WalletFlow({required this.wallet, required this.onDone});
  final PaymentProvider wallet;
  final ValueChanged<String> onDone;

  @override
  State<_WalletFlow> createState() => _WalletFlowState();
}

class _WalletFlowState extends State<_WalletFlow> {
  String _pin = '';

  void _tap(String d) {
    if (_pin.length >= 6) return;
    HapticFeedback.selectionClick();
    setState(() => _pin += d);
    if (_pin.length == 6) {
      final pin = _pin;
      Future.delayed(const Duration(milliseconds: 250), () {
        if (mounted) {
          widget.onDone(pin == declineTestCode ? 'failed' : 'success');
        }
      });
    }
  }

  void _back() {
    if (_pin.isNotEmpty) setState(() => _pin = _pin.substring(0, _pin.length - 1));
  }

  @override
  void dispose() {
    _pin = '';
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final w = widget.wallet;
    return Column(children: [
      Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          gradient: LinearGradient(
              colors: [w.color, Color.lerp(w.color, Colors.black, 0.25)!]),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(children: [
          Icon(Icons.account_balance_wallet, color: w.onColor, size: 30),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(w.name,
                  style: TextStyle(
                      color: w.onColor, fontWeight: FontWeight.w800)),
              Text('Linked account •••• 2207',
                  style: TextStyle(
                      color: w.onColor.withValues(alpha: 0.8), fontSize: 12)),
            ]),
          ),
        ]),
      ),
      const SizedBox(height: 22),
      Text('Enter your 6-digit PIN',
          style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 14),
      Row(mainAxisAlignment: MainAxisAlignment.center, children: [
        for (var i = 0; i < 6; i++)
          AnimatedContainer(
            duration: const Duration(milliseconds: 150),
            margin: const EdgeInsets.symmetric(horizontal: 7),
            width: 16,
            height: 16,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: i < _pin.length ? w.color : Colors.transparent,
              border: Border.all(color: w.color, width: 2),
            ),
          ),
      ]),
      const SizedBox(height: 18),
      _PinPad(onDigit: _tap, onBack: _back),
    ]);
  }
}

class _PinPad extends StatelessWidget {
  const _PinPad({required this.onDigit, required this.onBack});
  final ValueChanged<String> onDigit;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    Widget key(String label, {VoidCallback? onTap, IconData? icon}) => Expanded(
          child: Padding(
            padding: const EdgeInsets.all(6),
            child: Material(
              color: kCard,
              borderRadius: BorderRadius.circular(18),
              child: InkWell(
                key: Key('pin-$label'),
                borderRadius: BorderRadius.circular(18),
                onTap: onTap,
                child: SizedBox(
                  height: 58,
                  child: Center(
                    child: icon != null
                        ? Icon(icon)
                        : Text(label,
                            style: const TextStyle(
                                fontSize: 22, fontWeight: FontWeight.w700)),
                  ),
                ),
              ),
            ),
          ),
        );
    Widget row(List<String> ds) => Row(children: [
          for (final d in ds) key(d, onTap: () => onDigit(d)),
        ]);
    return Column(children: [
      row(['1', '2', '3']),
      row(['4', '5', '6']),
      row(['7', '8', '9']),
      Row(children: [
        const Expanded(child: SizedBox()),
        key('0', onTap: () => onDigit('0')),
        key('back', onTap: onBack, icon: Icons.backspace_outlined),
      ]),
    ]);
  }
}

// ---------------------------------------------------------------------------
// DuitNow QR: scannable code with a 5-minute expiry.

class _DuitNowFlow extends StatefulWidget {
  const _DuitNowFlow(
      {required this.reference,
      required this.amountSen,
      required this.onDone});
  final String reference;
  final int amountSen;
  final ValueChanged<String> onDone;

  @override
  State<_DuitNowFlow> createState() => _DuitNowFlowState();
}

class _DuitNowFlowState extends State<_DuitNowFlow> {
  static const _validFor = Duration(minutes: 5);
  late final DateTime _expires = DateTime.now().add(_validFor);
  Timer? _tick;
  Duration _left = _validFor;
  bool _checking = false;

  @override
  void initState() {
    super.initState();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      final left = _expires.difference(DateTime.now());
      if (!mounted) return;
      if (left <= Duration.zero) {
        _tick?.cancel();
        widget.onDone('failed');
        return;
      }
      setState(() => _left = left);
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  Future<void> _paid() async {
    setState(() => _checking = true);
    await Future.delayed(const Duration(milliseconds: 900));
    if (mounted) widget.onDone('success');
  }

  @override
  Widget build(BuildContext context) {
    final mm = _left.inMinutes.remainder(60).toString().padLeft(2, '0');
    final ss = _left.inSeconds.remainder(60).toString().padLeft(2, '0');
    final progress = _left.inSeconds / _validFor.inSeconds;
    // Prototype payload only; not an EMVCo DuitNow merchant code.
    final payload = 'SAGEMAKER-PROTOTYPE|REF=${widget.reference}'
        '|AMT=${(widget.amountSen / 100).toStringAsFixed(2)}|CUR=MYR';
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: kCard,
        borderRadius: BorderRadius.circular(24),
        boxShadow: softShadow(),
      ),
      child: Column(children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
          decoration: BoxDecoration(
            color: duitNowProvider.color,
            borderRadius: BorderRadius.circular(999),
          ),
          child: const Text('DuitNow QR',
              style: TextStyle(
                  color: Colors.white, fontWeight: FontWeight.w800)),
        ),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            border: Border.all(color: duitNowProvider.color, width: 3),
            borderRadius: BorderRadius.circular(20),
          ),
          child: QrImageView(
            key: const Key('duitnow-qr'),
            data: payload,
            size: min(MediaQuery.sizeOf(context).width - 120, 230),
            eyeStyle: const QrEyeStyle(
                eyeShape: QrEyeShape.square, color: kText),
            dataModuleStyle: const QrDataModuleStyle(
                dataModuleShape: QrDataModuleShape.circle, color: kText),
          ),
        ),
        const SizedBox(height: 16),
        const Text(
            'Scan with any Malaysian banking or e-wallet app that supports DuitNow QR.',
            textAlign: TextAlign.center),
        const SizedBox(height: 14),
        Row(children: [
          const Icon(Icons.timer_outlined, size: 18, color: kMuted),
          const SizedBox(width: 6),
          Text('Expires in $mm:$ss',
              key: const Key('duitnow-timer'),
              style: const TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(width: 12),
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(99),
              child: LinearProgressIndicator(
                  value: progress,
                  minHeight: 6,
                  color: duitNowProvider.color),
            ),
          ),
        ]),
        const SizedBox(height: 18),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            key: const Key('duitnow-paid'),
            onPressed: _checking ? null : _paid,
            icon: _checking
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.white))
                : const Icon(Icons.verified_outlined),
            label: Text(_checking ? 'Checking payment...' : "I've paid"),
          ),
        ),
      ]),
    );
  }
}

// ---------------------------------------------------------------------------
// Card: number, expiry, CVV, then 3-D Secure OTP.

class _CardFlow extends StatefulWidget {
  const _CardFlow({required this.amountSen, required this.onDone});
  final int amountSen;
  final ValueChanged<String> onDone;

  @override
  State<_CardFlow> createState() => _CardFlowState();
}

class _CardFlowState extends State<_CardFlow> {
  final _number = TextEditingController();
  final _name = TextEditingController();
  final _expiry = TextEditingController();
  final _cvv = TextEditingController();
  final _otp = TextEditingController();
  bool _otpStage = false;
  final _errors = <String, String>{};

  @override
  void initState() {
    super.initState();
    for (final c in [_number, _name, _expiry]) {
      c.addListener(() => setState(() {}));
    }
  }

  @override
  void dispose() {
    for (final c in [_number, _name, _expiry, _cvv, _otp]) {
      c.clear();
      c.dispose();
    }
    super.dispose();
  }

  String get _digits => _number.text.replaceAll(' ', '');

  void _pay() {
    _errors.clear();
    if (!luhnValid(_digits)) _errors['number'] = 'Enter a valid card number.';
    if (_name.text.trim().length < 2) _errors['name'] = 'Enter the name on the card.';
    if (!expiryValid(_expiry.text)) _errors['expiry'] = 'Use a future MM/YY date.';
    final cvvLen = cardBrand(_digits) == 'AMEX' ? 4 : 3;
    if (_cvv.text.length != cvvLen) _errors['cvv'] = '$cvvLen digits.';
    if (_errors.isNotEmpty) {
      setState(() {});
      return;
    }
    // Card details are dropped before the OTP step; only the result is kept.
    _cvv.clear();
    setState(() => _otpStage = true);
  }

  void _verify() {
    final otp = _otp.text.trim();
    if (!RegExp(r'^\d{6}$').hasMatch(otp)) {
      setState(() => _errors['otp'] = 'The OTP has 6 digits.');
      return;
    }
    widget.onDone(otp == declineTestCode ? 'failed' : 'success');
  }

  @override
  Widget build(BuildContext context) {
    final brand = cardBrand(_digits);
    final last4 = _digits.length >= 4 ? _digits.substring(_digits.length - 4) : '••••';
    if (_otpStage) {
      return Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          color: kCard,
          borderRadius: BorderRadius.circular(22),
          boxShadow: softShadow(),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            const Icon(Icons.shield_outlined, color: kPrimary),
            const SizedBox(width: 8),
            Text('3-D Secure verification',
                style: Theme.of(context).textTheme.titleMedium),
          ]),
          const SizedBox(height: 10),
          Text('Your bank sent a one-time password to the phone number linked '
              'to ${brand ?? 'your card'} ending $last4.'),
          const SizedBox(height: 14),
          TextField(
            key: const Key('card-otp'),
            controller: _otp,
            autofocus: true,
            keyboardType: TextInputType.number,
            maxLength: 6,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 24, letterSpacing: 10),
            decoration: InputDecoration(
                counterText: '', hintText: '••••••', errorText: _errors['otp']),
            onSubmitted: (_) => _verify(),
          ),
          const SizedBox(height: 14),
          FilledButton(
              key: const Key('card-verify'),
              onPressed: _verify,
              child: const Text('Verify and pay')),
        ]),
      );
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _CardPreview(
        number: _number.text,
        name: _name.text,
        expiry: _expiry.text,
        brand: brand,
      ),
      const SizedBox(height: 18),
      TextField(
        key: const Key('card-number'),
        controller: _number,
        keyboardType: TextInputType.number,
        autocorrect: false,
        enableSuggestions: false,
        inputFormatters: [
          FilteringTextInputFormatter.digitsOnly,
          LengthLimitingTextInputFormatter(19),
          _CardNumberFormatter(),
        ],
        decoration: InputDecoration(
          labelText: 'Card number',
          prefixIcon: const Icon(Icons.credit_card),
          errorText: _errors['number'],
        ),
      ),
      const SizedBox(height: 10),
      TextField(
        key: const Key('card-name'),
        controller: _name,
        textCapitalization: TextCapitalization.characters,
        autocorrect: false,
        decoration: InputDecoration(
            labelText: 'Name on card', errorText: _errors['name']),
      ),
      const SizedBox(height: 10),
      Row(children: [
        Expanded(
          child: TextField(
            key: const Key('card-expiry'),
            controller: _expiry,
            keyboardType: TextInputType.number,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(4),
              _ExpiryFormatter(),
            ],
            decoration: InputDecoration(
                labelText: 'Expiry (MM/YY)', errorText: _errors['expiry']),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: TextField(
            key: const Key('card-cvv'),
            controller: _cvv,
            keyboardType: TextInputType.number,
            obscureText: true,
            inputFormatters: [
              FilteringTextInputFormatter.digitsOnly,
              LengthLimitingTextInputFormatter(4),
            ],
            decoration:
                InputDecoration(labelText: 'CVV', errorText: _errors['cvv']),
          ),
        ),
      ]),
      const SizedBox(height: 16),
      FilledButton.icon(
        key: const Key('card-pay'),
        onPressed: _pay,
        icon: const Icon(Icons.lock_outline),
        label: Text('Pay ${formatRm(widget.amountSen)}'),
      ),
      const SizedBox(height: 8),
      const Text('Test card: 4111 1111 1111 1111, any future expiry, any CVV.',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 12, color: kMuted)),
    ]);
  }
}

class _CardPreview extends StatelessWidget {
  const _CardPreview(
      {required this.number,
      required this.name,
      required this.expiry,
      required this.brand});
  final String number;
  final String name;
  final String expiry;
  final String? brand;

  @override
  Widget build(BuildContext context) {
    final shown = number.isEmpty ? '•••• •••• •••• ••••' : number;
    return AspectRatio(
      aspectRatio: 1.6,
      child: Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF1D2A25), kPrimary, Color(0xFF2E5E4E)],
          ),
          borderRadius: BorderRadius.circular(22),
          boxShadow: softShadow(0.25),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Container(
              width: 42,
              height: 30,
              decoration: BoxDecoration(
                gradient: kGoldGradient,
                borderRadius: BorderRadius.circular(6),
              ),
            ),
            const Spacer(),
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 250),
              child: Text(brand ?? '',
                  key: ValueKey(brand),
                  style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                      fontStyle: FontStyle.italic,
                      fontSize: 18)),
            ),
          ]),
          const Spacer(),
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(shown,
                style: const TextStyle(
                    color: Colors.white,
                    fontSize: 22,
                    letterSpacing: 2,
                    fontWeight: FontWeight.w600)),
          ),
          const SizedBox(height: 14),
          Row(children: [
            Expanded(
              child: Text(name.isEmpty ? 'CARDHOLDER NAME' : name.toUpperCase(),
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white70, fontSize: 12)),
            ),
            Text(expiry.isEmpty ? 'MM/YY' : expiry,
                style: const TextStyle(color: Colors.white70, fontSize: 12)),
          ]),
        ]),
      ),
    );
  }
}

class _CardNumberFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(
      TextEditingValue oldValue, TextEditingValue newValue) {
    final d = newValue.text.replaceAll(' ', '');
    final b = StringBuffer();
    for (var i = 0; i < d.length; i++) {
      if (i > 0 && i % 4 == 0) b.write(' ');
      b.write(d[i]);
    }
    final t = b.toString();
    return TextEditingValue(
        text: t, selection: TextSelection.collapsed(offset: t.length));
  }
}

class _ExpiryFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(
      TextEditingValue oldValue, TextEditingValue newValue) {
    final d = newValue.text.replaceAll('/', '');
    final t = d.length > 2 ? '${d.substring(0, 2)}/${d.substring(2)}' : d;
    return TextEditingValue(
        text: t, selection: TextSelection.collapsed(offset: t.length));
  }
}

/// Re-exported so callers only import this file for the summary text.
String gatewaySummary(PaymentChannel? c, String? providerId) =>
    paymentSummary(c, providerId);
