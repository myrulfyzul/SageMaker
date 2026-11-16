/// Artisan profile as served to staff by `/api/staff/artisans` (Req 23).
/// Private contact details exist only in this staff model (Req 23.4).
class Artisan {
  const Artisan({
    required this.id,
    required this.name,
    required this.specialisation,
    required this.availability,
    this.story = '',
    this.phone,
    this.email,
    this.address,
    this.assignedProducts = const [],
    this.openJobCount,
    this.completedJobCount,
  });

  factory Artisan.fromJson(Map<String, dynamic> json) {
    final contact = json['privateContact'] is Map
        ? Map<String, dynamic>.from(json['privateContact'] as Map)
        : const <String, dynamic>{};
    String? text(Object? v) {
      final s = v?.toString() ?? '';
      return s.isEmpty ? null : s;
    }

    return Artisan(
      id: (json['id'] as num).toInt(),
      name: (json['name'] ?? '').toString(),
      specialisation: (json['specialisation'] ?? '').toString(),
      availability: (json['availability'] ?? 'available').toString(),
      story: (json['story'] ?? '').toString(),
      phone: text(contact['phone']),
      email: text(contact['email']),
      address: text(contact['address']),
      assignedProducts: [
        for (final p in (json['assignedProducts'] as List? ?? const []))
          if (p is Map) (p['name'] ?? p['id'] ?? '').toString(),
      ],
      openJobCount: (json['openJobCount'] as num?)?.toInt(),
      completedJobCount: (json['completedJobCount'] as num?)?.toInt(),
    );
  }

  final int id;
  final String name;
  final String specialisation;

  /// `available`, `busy` or `unavailable`.
  final String availability;
  final String story;
  final String? phone;
  final String? email;
  final String? address;
  final List<String> assignedProducts;
  final int? openJobCount;
  final int? completedJobCount;
}

/// Result of saving an artisan: the profile plus the open job ids that make
/// an `unavailable` change risky (Req 23.6).
class ArtisanSaveResult {
  const ArtisanSaveResult(this.artisan, this.warningJobIds);

  final Artisan artisan;
  final List<int> warningJobIds;
}

const artisanAvailabilities = ['available', 'busy', 'unavailable'];
