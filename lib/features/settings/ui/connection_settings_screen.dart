import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/config/api_config.dart';
import '../../../core/network/api_client.dart';
import '../../../core/network/app_failure.dart';
import '../../../core/validators.dart';

/// Connection settings: shows the URL in use, validates and saves an
/// override, clears it, and checks reachability with the URL in the error
/// (Req 2.3 to 2.6).
class ConnectionSettingsScreen extends ConsumerStatefulWidget {
  const ConnectionSettingsScreen({super.key});

  @override
  ConsumerState<ConnectionSettingsScreen> createState() => _State();
}

class _State extends ConsumerState<ConnectionSettingsScreen> {
  final _key = GlobalKey<FormState>();
  final _controller = TextEditingController();
  bool _filled = false;
  bool _checking = false;
  String? _saveError;
  String? _status;
  String? _unreachable;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _saveError = null;
      _status = null;
    });
    if (!_key.currentState!.validate()) return;
    try {
      await ref.read(apiConfigProvider.notifier).saveOverride(_controller.text);
      if (!mounted) return;
      setState(() => _status = 'Saved');
      await _check();
    } on InvalidApiBaseUrl catch (e) {
      if (mounted) setState(() => _saveError = e.toString());
    }
  }

  Future<void> _clear() async {
    await ref.read(apiConfigProvider.notifier).clearOverride();
    if (!mounted) return;
    _controller.text = ref.read(apiConfigProvider).value ?? '';
    setState(() {
      _status = 'Cleared. Using the default URL.';
      _saveError = null;
      _unreachable = null;
    });
  }

  Future<void> _check() async {
    setState(() {
      _checking = true;
      _unreachable = null;
    });
    final client = ref.read(apiClientProvider);
    try {
      await client.checkReachable();
      if (mounted) setState(() => _status = 'Server reachable');
    } on AppFailure catch (e) {
      // 401 or 4xx still prove the server answered.
      if (e is NetworkFailure || e is TimeoutFailure || e is ServerFailure) {
        if (mounted) {
          setState(() => _unreachable =
              'The server could not be reached at ${client.baseUrl}');
        }
      } else if (mounted) {
        setState(() => _status = 'Server reachable');
      }
    } finally {
      if (mounted) setState(() => _checking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final url = ref.watch(apiConfigProvider);
    if (!_filled && url.hasValue) {
      _filled = true;
      _controller.text = url.requireValue;
    }
    return Scaffold(
      appBar: AppBar(title: const Text('Connection settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Server in use', style: Theme.of(context).textTheme.labelLarge),
          const SizedBox(height: 4),
          SelectableText(url.value ?? 'Loading...',
              key: const ValueKey('url-in-use')),
          const SizedBox(height: 16),
          Form(
            key: _key,
            child: TextFormField(
              key: const ValueKey('url-field'),
              controller: _controller,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(labelText: 'API base URL'),
              validator: (v) {
                final t = v?.trim() ?? '';
                if (t.length > maxApiBaseUrlLength) {
                  return 'At most $maxApiBaseUrlLength characters';
                }
                return validateUrl(t);
              },
            ),
          ),
          if (_saveError != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_saveError!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          const SizedBox(height: 12),
          Row(children: [
            FilledButton(
                key: const ValueKey('url-save'),
                onPressed: _save,
                child: const Text('Save')),
            const SizedBox(width: 12),
            OutlinedButton(
                key: const ValueKey('url-clear'),
                onPressed: _clear,
                child: const Text('Clear')),
          ]),
          if (_status != null)
            Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(_status!, key: const ValueKey('url-status'))),
          if (_checking)
            const Padding(
                padding: EdgeInsets.only(top: 12),
                child: LinearProgressIndicator()),
          if (_unreachable != null) ...[
            const SizedBox(height: 12),
            Text(_unreachable!,
                key: const ValueKey('url-unreachable'),
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerLeft,
              child: FilledButton(
                  key: const ValueKey('url-retry'),
                  onPressed: _checking ? null : _check,
                  child: const Text('Retry')),
            ),
          ] else
            TextButton(
                key: const ValueKey('url-test'),
                onPressed: _checking ? null : _check,
                child: const Text('Test connection')),
        ],
      ),
    );
  }
}
