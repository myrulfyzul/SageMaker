import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/app_failure.dart';
import '../../../core/validators.dart';
import '../state/auth_actions.dart';
import '../../../app/theme.dart';
import '../../../core/widgets/ui_kit.dart';
import 'login_screen.dart' show loginErrorMessage;

// Tooltips for the visibility toggle.
const _revealTip = 'Show password';
const _concealTip = 'Hide password';

/// Name rule of the registration endpoint: 1 to 100 characters (Req 4.1).
String? validateRegisterName(String? value) {
  final v = value?.trim() ?? '';
  if (v.isEmpty || v.length > 100) return 'Name must be 1 to 100 characters';
  return null;
}

/// Registration screen (Req 4.1, 4.4, 33.6).
class RegisterScreen extends ConsumerStatefulWidget {
  const RegisterScreen({super.key});

  @override
  ConsumerState<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends ConsumerState<RegisterScreen> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _busy = false;
  bool _obscure = true;
  String? _error;

  /// Reasons returned by the server (422 or 409), keyed by field name.
  Map<String, String> _serverErrors = const {};

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  String? _field(String name, String? local) => local ?? _serverErrors[name];

  Future<void> _submit() async {
    if (_busy) return;
    setState(() => _serverErrors = const {});
    if (!_form.currentState!.validate()) return;
    final messenger = ScaffoldMessenger.of(context);
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final (_, report) = await ref
          .read(authActionsProvider)
          .register(_name.text, _email.text, _password.text);
      final message = report.message;
      if (message != null) {
        messenger.showSnackBar(SnackBar(content: Text(message)));
      }
    } on ValidationFailure catch (e) {
      if (!mounted) return;
      setState(() {
        _serverErrors = e.fields;
        _error = e.fields.isEmpty ? e.message : null;
      });
      _form.currentState!.validate();
    } on ConflictFailure catch (e) {
      if (!mounted) return;
      setState(
          () => _serverErrors = {'email': 'This email is already registered'});
      _form.currentState!.validate();
      if (e.code.isEmpty) setState(() => _error = e.message);
    } on UnauthorizedFailure {
      // The account exists but the follow-up sign-in failed.
      if (mounted) {
        setState(() =>
            _error = 'Account created. Please sign in with your new details.');
      }
    } on AppFailure catch (e) {
      if (mounted) {
        setState(() => _error = e is ServerFailure
            ? 'Registration failed. Please try again.'
            : loginErrorMessage(e));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Create account'),
        leading: IconButton(
          tooltip: 'Back',
          icon: const Icon(Icons.arrow_back),
          onPressed: () =>
              context.canPop() ? context.pop() : context.go('/login'),
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
                const GradientPanel(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(Icons.auto_awesome, color: kAccent, size: 30),
                      SizedBox(height: 10),
                      Text('Join SageMaker',
                          style: TextStyle(
                              fontFamily: kDisplayFont,
                              color: Colors.white,
                              fontSize: 26,
                              fontWeight: FontWeight.w700)),
                      SizedBox(height: 4),
                      Text(
                          'Save favourites, track orders and request custom pieces.',
                          style: TextStyle(color: Colors.white70)),
                    ],
                  ),
                ),
                const SizedBox(height: 20),
                TextFormField(
                  controller: _name,
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(
                      labelText: 'Name', prefixIcon: Icon(Icons.person_outline)),
                  validator: (v) => _field('name', validateRegisterName(v)),
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _email,
                  keyboardType: TextInputType.emailAddress,
                  autofillHints: const [AutofillHints.email],
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(
                      labelText: 'Email', prefixIcon: Icon(Icons.mail_outline)),
                  validator: (v) => _field('email', validateEmail(v)),
                ),
                const SizedBox(height: 12),
                TextFormField(
                  controller: _password,
                  obscureText: _obscure,
                  onFieldSubmitted: (_) => _submit(),
                  decoration: InputDecoration(
                    labelText: 'Password',
                    helperText: '8 to 128 characters with a letter and a digit',
                    suffixIcon: IconButton(
                      tooltip: _obscure ? _revealTip : _concealTip,
                      icon: Icon(
                          _obscure ? Icons.visibility : Icons.visibility_off),
                      onPressed: () => setState(() => _obscure = !_obscure),
                    ),
                  ),
                  validator: (v) => _field('password', validatePassword(v)),
                ),
                if (_error != null) ...[
                  const SizedBox(height: 12),
                  Semantics(
                    liveRegion: true,
                    child: Text(_error!,
                        key: const Key('register-error'),
                        style: TextStyle(color: scheme.error)),
                  ),
                ],
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: _busy ? null : _submit,
                  child: _busy
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('Create account'),
                ),
                TextButton(
                  onPressed: () => context.go('/login'),
                  child: const Text('I already have an account'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
