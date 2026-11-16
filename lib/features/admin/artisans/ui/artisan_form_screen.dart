import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/app_failure.dart';
import '../../../../core/widgets/async_value_view.dart';
import '../data/artisan_models.dart';
import '../data/artisan_validation.dart';
import '../state/artisans_provider.dart';
import 'artisans_screen.dart' show availabilityLabel;

/// Create or edit an artisan. Private contact fields are shown to staff only
/// (Req 23.4). Saving `unavailable` with open jobs shows a warning listing
/// the job ids (Req 23.6). Edit mode also shows assigned products and job
/// counts (Req 23.3).
class ArtisanFormScreen extends ConsumerWidget {
  const ArtisanFormScreen({super.key, this.artisanId});

  final int? artisanId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final id = artisanId;
    if (id == null) return const _ArtisanForm(artisan: null);
    final value = ref.watch(artisanProvider(id));
    return value.when(
      data: (a) => _ArtisanForm(artisan: a),
      loading: () => Scaffold(
          appBar: AppBar(title: const Text('Artisan')),
          body: const Center(child: CircularProgressIndicator())),
      error: (e, _) => Scaffold(
        appBar: AppBar(title: const Text('Artisan')),
        body: AsyncValueView<void>(
          value: AsyncError<void>(e, StackTrace.empty),
          data: (_) => const SizedBox(),
          onRetry: () => ref.invalidate(artisanProvider(id)),
          onEmptyAction: () {},
          errorMessage: (e) => e is AppFailure ? e.message : 'Server error',
        ),
      ),
    );
  }
}

class _ArtisanForm extends ConsumerStatefulWidget {
  const _ArtisanForm({required this.artisan});

  final Artisan? artisan;

  @override
  ConsumerState<_ArtisanForm> createState() => _ArtisanFormState();
}

class _ArtisanFormState extends ConsumerState<_ArtisanForm> {
  final _key = GlobalKey<FormState>();
  late final _name = TextEditingController(text: widget.artisan?.name);
  late final _spec =
      TextEditingController(text: widget.artisan?.specialisation);
  late final _story = TextEditingController(text: widget.artisan?.story);
  late final _phone = TextEditingController(text: widget.artisan?.phone);
  late final _email = TextEditingController(text: widget.artisan?.email);
  late final _address = TextEditingController(text: widget.artisan?.address);
  late String _availability = widget.artisan?.availability ?? 'available';
  Map<String, String> _serverErrors = {};
  List<int> _warningJobs = [];
  String? _error;
  bool _saving = false;

  @override
  void dispose() {
    for (final c in [_name, _spec, _story, _phone, _email, _address]) {
      c.dispose();
    }
    super.dispose();
  }

  String? _combine(String field, String? local) =>
      local ?? _serverErrors[field];

  Future<void> _save() async {
    setState(() {
      _serverErrors = {};
      _error = null;
    });
    if (!_key.currentState!.validate()) return;
    setState(() => _saving = true);
    try {
      final result = await ref.read(artisansRepositoryProvider).save(
            id: widget.artisan?.id,
            name: _name.text,
            specialisation: _spec.text,
            availability: _availability,
            story: _story.text,
            phone: _phone.text,
            email: _email.text,
            address: _address.text,
          );
      if (!mounted) return;
      if (result.warningJobIds.isNotEmpty) {
        setState(() {
          _saving = false;
          _warningJobs = result.warningJobIds;
        });
        return;
      }
      Navigator.of(context).pop();
    } on ValidationFailure catch (e) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _serverErrors = e.fields;
        _error = e.fields.isEmpty ? e.message : null;
      });
      _key.currentState?.validate();
    } on AppFailure catch (e) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error = e.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final a = widget.artisan;
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: Text(a == null ? 'Add artisan' : 'Edit artisan')),
      body: Form(
        key: _key,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_warningJobs.isNotEmpty)
              Semantics(
                liveRegion: true,
                child: Card(
                  key: const ValueKey('unavailable-warning'),
                  color: scheme.errorContainer,
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Saved, but this artisan has open jobs.'),
                        Text('Open jobs: '
                            '${_warningJobs.map((j) => '#$j').join(', ')}'),
                        TextButton(
                          onPressed: () => Navigator.of(context).pop(),
                          child: const Text('Done'),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(_error!, style: TextStyle(color: scheme.error)),
              ),
            if (a != null) ...[
              Text('Open jobs: ${a.openJobCount ?? 0} · '
                  'Completed jobs: ${a.completedJobCount ?? 0}'),
              Text(a.assignedProducts.isEmpty
                  ? 'No assigned products'
                  : 'Products: ${a.assignedProducts.join(', ')}'),
              const SizedBox(height: 12),
            ],
            TextFormField(
              key: const ValueKey('artisan-name'),
              controller: _name,
              maxLength: 100,
              decoration: const InputDecoration(labelText: 'Name'),
              validator: (v) => _combine('name', validateArtisanName(v)),
            ),
            TextFormField(
              key: const ValueKey('artisan-specialisation'),
              controller: _spec,
              maxLength: 100,
              decoration: const InputDecoration(labelText: 'Specialisation'),
              validator: (v) =>
                  _combine('specialisation', validateSpecialisation(v)),
            ),
            DropdownButtonFormField<String>(
              key: const ValueKey('artisan-availability'),
              initialValue: _availability,
              decoration: const InputDecoration(labelText: 'Availability'),
              items: [
                for (final v in artisanAvailabilities)
                  DropdownMenuItem(value: v, child: Text(availabilityLabel(v))),
              ],
              onChanged: (v) => setState(() => _availability = v!),
            ),
            TextFormField(
              key: const ValueKey('artisan-story'),
              controller: _story,
              maxLength: 2000,
              maxLines: 3,
              decoration: const InputDecoration(labelText: 'Story (public)'),
              validator: (v) => _combine('story', validateStory(v)),
            ),
            const SizedBox(height: 8),
            Text('Private contact (staff only)',
                style: Theme.of(context).textTheme.titleSmall),
            TextFormField(
              key: const ValueKey('artisan-phone'),
              controller: _phone,
              maxLength: 30,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(labelText: 'Phone'),
              validator: (v) => _combine('phone', validateArtisanPhone(v)),
            ),
            TextFormField(
              key: const ValueKey('artisan-email'),
              controller: _email,
              maxLength: 254,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(labelText: 'Email'),
              validator: (v) => _combine('email', validateArtisanEmail(v)),
            ),
            TextFormField(
              key: const ValueKey('artisan-address'),
              controller: _address,
              maxLength: 300,
              maxLines: 2,
              decoration: const InputDecoration(labelText: 'Address'),
              validator: (v) => _combine('address', validateArtisanAddress(v)),
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: Text(_saving ? 'Saving…' : 'Save'),
            ),
          ],
        ),
      ),
    );
  }
}
