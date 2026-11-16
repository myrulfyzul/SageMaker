import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/navigation_memory.dart';
import '../../../core/network/app_failure.dart';
import '../../../core/widgets/demo_label.dart';
import '../state/auth_actions.dart';
import '../state/session_provider.dart';
import 'fictional_data_notice.dart';

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
    final scheme = Theme.of(context).colorScheme;
    final locked = _lockSeconds > 0;
    final error = locked
        ? 'Too many failed attempts. Try again in $_lockSeconds seconds.'
        : _error;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Sign in'),
        leading: IconButton(
          tooltip: 'Cancel',
          icon: const Icon(Icons.close),
          onPressed: () => cancelLogin(
              GoRouter.of(context), ref.read(navigationMemoryProvider)),
        ),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Form(
            key: _form,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Align(
                    alignment: Alignment.centerLeft,
                    child: DemoLabel.prototype()),
                const SizedBox(height: 12),
                if (session is SessionServerUnreachable) ...[
                  Text(session.message,
                      style: TextStyle(color: scheme.error),
                      key: const Key('unreachable-error')),
                  const SizedBox(height: 12),
                ],
                TextFormField(
                  controller: _email,
                  keyboardType: TextInputType.emailAddress,
                  autofillHints: const [AutofillHints.email],
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(labelText: 'Email'),
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
                    suffixIcon: IconButton(
                      tooltip: _obscure ? _revealTip : _concealTip,
                      icon: Icon(
                          _obscure ? Icons.visibility : Icons.visibility_off),
                      onPressed: () => setState(() => _obscure = !_obscure),
                    ),
                  ),
                  validator: (v) =>
                      (v == null || v.isEmpty) ? 'Enter your password' : null,
                ),
                if (error != null) ...[
                  const SizedBox(height: 12),
                  Semantics(
                    liveRegion: true,
                    child: Text(error,
                        key: const Key('login-error'),
                        style: TextStyle(color: scheme.error)),
                  ),
                ],
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: (_busy || locked) ? null : _submit,
                  child: _busy
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('Sign in'),
                ),
                TextButton(
                  onPressed: () => context.push('/register'),
                  child: const Text('Create an account'),
                ),
                const SizedBox(height: 8),
                const FictionalDataNotice(),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
