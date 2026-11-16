import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';

class Profile {
  const Profile(
      {required this.id, required this.name, required this.email, this.phone});

  factory Profile.fromJson(Map<String, dynamic> j) => Profile(
        id: (j['id'] as num?)?.toInt() ?? 0,
        name: (j['name'] ?? '').toString(),
        email: (j['email'] ?? '').toString(),
        phone: j['phone']?.toString(),
      );

  final int id;
  final String name;
  final String email;
  final String? phone;
}

class SavedAddress {
  const SavedAddress({
    required this.id,
    required this.recipientName,
    required this.phone,
    required this.line1,
    this.line2,
    required this.postcode,
    required this.city,
    required this.state,
    required this.isDefault,
  });

  factory SavedAddress.fromJson(Map<String, dynamic> j) => SavedAddress(
        id: (j['id'] as num).toInt(),
        recipientName: (j['recipientName'] ?? '').toString(),
        phone: (j['phone'] ?? '').toString(),
        line1: (j['line1'] ?? '').toString(),
        line2: j['line2']?.toString(),
        postcode: (j['postcode'] ?? '').toString(),
        city: (j['city'] ?? '').toString(),
        state: (j['state'] ?? '').toString(),
        isDefault: j['isDefault'] == true,
      );

  final int id;
  final String recipientName;
  final String phone;
  final String line1;
  final String? line2;
  final String postcode;
  final String city;
  final String state;
  final bool isDefault;
}

/// Body for creating or updating an address.
Map<String, Object?> addressBody({
  required String recipientName,
  required String phone,
  required String line1,
  String? line2,
  required String postcode,
  required String city,
  required String state,
  required bool isDefault,
}) =>
    {
      'recipientName': recipientName.trim(),
      'phone': phone.trim(),
      'line1': line1.trim(),
      if (line2 != null && line2.trim().isNotEmpty) 'line2': line2.trim(),
      'postcode': postcode.trim(),
      'city': city.trim(),
      'state': state.trim(),
      'isDefault': isDefault,
    };

class ProfileRepository {
  ProfileRepository(this._client);
  final ApiClient _client;

  Future<Profile> get() async => Profile.fromJson(
      Map<String, dynamic>.from(await _client.get('/api/me') as Map));

  Future<Profile> update(String name, String phone) async => Profile.fromJson(
      Map<String, dynamic>.from(await _client.put('/api/me',
          body: {'name': name.trim(), 'phone': phone.trim()}) as Map));

  Future<List<SavedAddress>> addresses() async {
    final data = await _client.get('/api/me/addresses');
    return [
      for (final a in (data as List? ?? const []))
        SavedAddress.fromJson(Map<String, dynamic>.from(a as Map)),
    ];
  }

  Future<void> create(Map<String, Object?> body) =>
      _client.post('/api/me/addresses', body: body);

  Future<void> updateAddress(int id, Map<String, Object?> body) =>
      _client.put('/api/me/addresses/$id', body: body);

  Future<void> setDefault(int id) =>
      _client.put('/api/me/addresses/$id/default');

  Future<void> delete(int id) => _client.delete('/api/me/addresses/$id');
}

final profileRepositoryProvider = Provider<ProfileRepository>(
    (ref) => ProfileRepository(ref.watch(apiClientProvider)));

final profileProvider = FutureProvider.autoDispose<Profile>(
    (ref) => ref.watch(profileRepositoryProvider).get());

final addressesProvider = FutureProvider.autoDispose<List<SavedAddress>>(
    (ref) => ref.watch(profileRepositoryProvider).addresses());
