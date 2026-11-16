import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/navigation_memory.dart';
import '../../../core/network/app_failure.dart';
import '../../../app/theme.dart';
import '../../../core/widgets/ui_kit.dart';
import '../state/auth_actions.dart';
import '../state/session_provider.dart';

// Tooltips for the visibility toggle.
const _revealTip = 'Show password';
const _concealTip = 'Hide password';

/// Message for a failed sign-in. The 401 text is the same for every cause
/// (Req 5.2).
String loginErrorMessage(AppFailure e) => switch (e) {
      UnauthorizedFailure() => 'Email or password is incorrect',
      RateLimitedFailure(:final retryAfterSeconds) => retryAfterSeconds == null
          ? 'Too many failed attempts. Please wait a few minutes and try again.'
          : 'Too many failed attempts. Try again in $retryAfterSeconds seconds.',
      NetworkFailure() ||
      TimeoutFailure() =>
        'The server could not be reached. Check your connection and try again.',
      _ => e.message,
    };

/// Login screen (Req 3.7, 5.1 to 5.3).
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  bool _obscure = true;
  String? _error;
  int _lockSeconds = 0;
  Timer? _timer;

  @override
  void dispose() {
    _timer?.cancel();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  void _startLockout(int seconds) {
    _timer?.cancel();
    setState(() => _lockSeconds = seconds);
    _timer = Timer.periodic(const Duration(seconds: 1), (t) {
      if (!mounted) return t.cancel();
      setState(() => _lockSeconds--);
      if (_lockSeconds <= 0) {
        t.cancel();
        setState(() => _error = null);
      }
    });
  }

  Future<void> _submit() async {
    if (_busy || _lockSeconds > 0 || !_form.currentState!.validate()) return;
    // The root messenger outlives this screen, which the router replaces.
    final messenger = ScaffoldMessenger.of(context);
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final (_, report) = await ref
          .read(authActionsProvider)
          .login(_email.text, _password.text);
      final message = report.message;
      if (message != null) {
        messenger.showSnackBar(SnackBar(content: Text(message)));
      }
    } on RateLimitedFailure catch (e) {
      if (!mounted) return;
      setState(() => _error = loginErrorMessage(e));
      final s = e.retryAfterSeconds;
      if (s != null && s > 0) _startLockout(s);
    } on AppFailure catch (e) {
      if (mounted) setState(() => _error = loginErrorMessage(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = ref.watch(sessionProvider);
    final locked = _lockSeconds > 0;
    final error = locked
        ? 'Too many failed attempts. Try again in $_lockSeconds seconds.'
        : _error;
    return Scaffold(
      body: Stack(children: [
        const _BrandBackdrop(),
        SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: IconButton(
                    tooltip: 'Cancel',
                    color: Colors.white,
                    icon: const Icon(Icons.close),
                    onPressed: () => cancelLogin(GoRouter.of(context),
                        ref.read(navigationMemoryProvider)),
                  ),
                ),
                const SizedBox(height: 8),
                const FadeSlideIn(child: _BrandTitle()),
                const SizedBox(height: 28),
                FadeSlideIn(
                  index: 2,
                  child: SoftCard(
                    padding: const EdgeInsets.all(22),
                    child: Form(
                      key: _form,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Text('Sign in',
                              style: Theme.of(context).textTheme.headlineMedium),
                          const SizedBox(height: 4),
                          Text('Welcome back. Sign in to shop and track your orders.',
                              style: Theme.of(context).textTheme.bodySmall),
                          const SizedBox(height: 18),
                          if (session is SessionServerUnreachable) ...[
                            Text(session.message,
                                style: const TextStyle(color: kError),
                                key: const Key('unreachable-error')),
                            const SizedBox(height: 12),
                          ],
                          TextFormField(
                            controller: _email,
                            keyboardType: TextInputType.emailAddress,
                            autofillHints: const [AutofillHints.email],
                            textInputAction: TextInputAction.next,
                            decoration: const InputDecoration(
                                labelText: 'Email',
                                prefixIcon: Icon(Icons.mail_outline)),
                            validator: (v) => (v == null || v.trim().isEmpty)
                                ? 'Enter your email'
                                : null,
                          ),
                          const SizedBox(height: 12),
                          TextFormField(
                            controller: _password,
                            obscureText: _obscure,
                            autofillHints: const [AutofillHints.password],
                            onFieldSubmitted: (_) => _submit(),
                            decoration: InputDecoration(
                              labelText: 'Password',
                              prefixIcon: const Icon(Icons.lock_outline),
                              suffixIcon: IconButton(
                                tooltip: _obscure ? _revealTip : _concealTip,
                                icon: Icon(_obscure
                                    ? Icons.visibility
                                    : Icons.visibility_off),
                                onPressed: () =>
                                    setState(() => _obscure = !_obscure),
                              ),
                            ),
                            validator: (v) => (v == null || v.isEmpty)
                                ? 'Enter your password'
                                : null,
                          ),
                          if (error != null) ...[
                            const SizedBox(height: 12),
                            Semantics(
                              liveRegion: true,
                              child: Text(error,
                                  key: const Key('login-error'),
                                  style: const TextStyle(color: kError)),
                            ),
                          ],
                          const SizedBox(height: 18),
                          FilledButton(
                            onPressed: (_busy || locked) ? null : _submit,
                            child: _busy
                                ? const SizedBox(
                                    height: 20,
                                    width: 20,
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2, color: Colors.white))
                                : const Text('Sign in'),
                          ),
                          const SizedBox(height: 6),
                          TextButton(
                            onPressed: () => context.push('/register'),
                            child: const Text('Create an account'),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ]),
    );
  }
}

/// Emerald gradient over the top of the screen with soft circles.
class _BrandBackdrop extends StatelessWidget {
  const _BrandBackdrop();

  @override
  Widget build(BuildContext context) => const Positioned(
        left: 0,
        right: 0,
        top: 0,
        height: 340,
        child: GradientPanel(radius: 0, child: SizedBox.expand()),
      );
}

class _BrandTitle extends StatelessWidget {
  const _BrandTitle();

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              gradient: kGoldGradient,
              borderRadius: BorderRadius.circular(18),
            ),
            alignment: Alignment.center,
            child: const Text('S',
                style: TextStyle(
                    fontFamily: kDisplayFont,
                    color: kPrimary,
                    fontSize: 32,
                    fontWeight: FontWeight.w700)),
          ),
          const SizedBox(height: 16),
          const Text('SageMaker',
              style: TextStyle(
                  fontFamily: kDisplayFont,
                  color: Colors.white,
                  fontSize: 34,
                  fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          const Text('Handmade with heart by women artisans.',
              style: TextStyle(color: Colors.white70, fontSize: 14)),
        ],
      );
}