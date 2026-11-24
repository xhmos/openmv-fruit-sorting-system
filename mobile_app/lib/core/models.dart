/// 与后端接口一一对应的数据结构
library;

Map<String, dynamic> asMap(dynamic value) {
  if (value is Map) return Map<String, dynamic>.from(value);
  return <String, dynamic>{};
}

List<Map<String, dynamic>> asMapList(dynamic value) {
  if (value is List) {
    return value.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
  }
  return const [];
}

int asInt(dynamic v, [int fallback = 0]) {
  if (v is int) return v;
  if (v is num) return v.toInt();
  return int.tryParse('$v') ?? fallback;
}

double asDouble(dynamic v, [double fallback = 0]) {
  if (v is num) return v.toDouble();
  return double.tryParse('$v') ?? fallback;
}

class UserInfo {
  const UserInfo({
    required this.id,
    required this.username,
    required this.role,
    required this.isActive,
    required this.avatar,
    required this.createTime,
  });

  final int id;
  final String username;
  final String role;
  final bool isActive;
  final String avatar;
  final String createTime;

  bool get isAdmin => role == 'admin';
  String get roleText => isAdmin ? '管理员' : '操作员';

  factory UserInfo.fromJson(Map<String, dynamic> json) => UserInfo(
        id: asInt(json['id']),
        username: '${json['username'] ?? ''}',
        role: '${json['role'] ?? 'operator'}',
        isActive: json['is_active'] == true,
        avatar: '${json['avatar'] ?? ''}',
        createTime: '${json['create_time'] ?? ''}',
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'username': username,
        'role': role,
        'is_active': isActive,
        'avatar': avatar,
        'create_time': createTime,
      };
}

class SortRecord {
  const SortRecord({
    required this.id,
    required this.fruitType,
    required this.result,
    required this.confidence,
    required this.area,
    required this.imgUrl,
    required this.createTime,
  });

  final int id;
  final String fruitType;
  final String result;
  final double confidence;
  final int area;
  final String imgUrl;
  final String createTime;

  bool get isGood => result == 'good';
  String get resultText => isGood ? '合格' : '剔除';
  int get confidencePercent => (confidence * 100).round();

  factory SortRecord.fromJson(Map<String, dynamic> json) {
    final img = '${json['img_url'] ?? ''}';
    return SortRecord(
      id: asInt(json['id']),
      fruitType: '${json['fruit_type'] ?? ''}',
      result: '${json['result'] ?? ''}',
      confidence: asDouble(json['confidence']),
      area: asInt(json['area']),
      imgUrl: img,
      createTime: '${json['create_time'] ?? ''}',
    );
  }
}

class FruitTypeCount {
  const FruitTypeCount({required this.name, required this.count});
  final String name;
  final int count;

  factory FruitTypeCount.fromJson(Map<String, dynamic> json) =>
      FruitTypeCount(name: '${json['name'] ?? ''}', count: asInt(json['count']));
}

class StatsData {
  const StatsData({
    required this.todayTotal,
    required this.todayGood,
    required this.todayBad,
    required this.goodRate,
    required this.labels,
    required this.totalSeries,
    required this.goodSeries,
    required this.rateSeries,
    required this.byType,
  });

  final int todayTotal;
  final int todayGood;
  final int todayBad;
  final double goodRate;
  final List<String> labels;
  final List<int> totalSeries;
  final List<int> goodSeries;
  final List<double> rateSeries;
  final List<FruitTypeCount> byType;

  int get maxSeries {
    var max = 0;
    for (final v in totalSeries) {
      if (v > max) max = v;
    }
    return max;
  }

  factory StatsData.fromJson(Map<String, dynamic> json) {
    final summary = asMap(json['summary']);
    final trend = asMap(json['trend']);
    final labels = (trend['labels'] is List) ? (trend['labels'] as List).map((e) => '$e').toList() : <String>[];
    final total = (trend['total'] is List) ? (trend['total'] as List).map((e) => asInt(e)).toList() : <int>[];
    final good = (trend['good'] is List) ? (trend['good'] as List).map((e) => asInt(e)).toList() : <int>[];
    final rate = (trend['rate'] is List) ? (trend['rate'] as List).map((e) => asDouble(e)).toList() : <double>[];
    return StatsData(
      todayTotal: asInt(summary['today_total']),
      todayGood: asInt(summary['today_good']),
      todayBad: asInt(summary['today_bad']),
      goodRate: asDouble(summary['good_rate']),
      labels: labels,
      totalSeries: total,
      goodSeries: good,
      rateSeries: rate,
      byType: asMapList(json['by_type']).map(FruitTypeCount.fromJson).toList(),
    );
  }
}

class CameraStatus {
  const CameraStatus(this.raw);

  final Map<String, dynamic> raw;

  bool get running => raw['running'] == true;
  String get source => '${raw['source'] ?? ''}';
  String get error => '${raw['error'] ?? ''}';
  int get fps => asInt(raw['fps'], 8);
  int get frames => asInt(raw['frames']);
  int get width => asInt(raw['width']);
  int get height => asInt(raw['height']);
  String get startedAt => '${raw['started_at'] ?? ''}';
  bool get detect => raw['detect'] == true;
  bool get snapshot => raw['snapshot'] == true;
  bool get record => raw['record'] == true;
  int get hits => asInt(raw['hits']);
  int get snapshots => asInt(raw['snapshots']);
  int get videos => asInt(raw['videos']);
  bool get videoSupported => raw['video_supported'] == true;
  int get minArea => asInt(raw['min_area'], 300);
  double get cooldown => asDouble(raw['cooldown'], 3);
  double get minConfidence => asDouble(raw['min_confidence'], 0.65);
}

class SavedDevice {
  const SavedDevice({
    required this.id,
    required this.name,
    required this.devType,
    required this.target,
    required this.note,
    required this.lastStatus,
    required this.lastMessage,
    required this.lastConnectTime,
  });

  final int id;
  final String name;
  final String devType;
  final String target;
  final String note;
  final String lastStatus;
  final String lastMessage;
  final String lastConnectTime;

  bool get isOk => lastStatus == 'ok';
  bool get isFail => lastStatus == 'fail';

  String get typeText {
    switch (devType) {
      case 'camera':
        return '摄像头';
      case 'serial':
        return '串口';
      case 'stream':
        return '网络流';
      default:
        return devType;
    }
  }

  factory SavedDevice.fromJson(Map<String, dynamic> json) => SavedDevice(
        id: asInt(json['id']),
        name: '${json['name'] ?? ''}',
        devType: '${json['dev_type'] ?? ''}',
        target: '${json['target'] ?? ''}',
        note: '${json['note'] ?? ''}',
        lastStatus: '${json['last_status'] ?? ''}',
        lastMessage: '${json['last_message'] ?? ''}',
        lastConnectTime: '${json['last_connect_time'] ?? ''}',
      );
}

class SettingItem {
  const SettingItem({required this.key, required this.value, required this.remark});

  final String key;
  final String value;
  final String remark;

  factory SettingItem.fromJson(Map<String, dynamic> json) => SettingItem(
        key: '${json['key'] ?? ''}',
        value: '${json['value'] ?? ''}',
        remark: '${json['remark'] ?? ''}',
      );
}

class VideoItem {
  const VideoItem({
    required this.name,
    required this.sizeText,
    required this.createTime,
    required this.url,
  });

  final String name;
  final String sizeText;
  final String createTime;
  final String url;

  factory VideoItem.fromJson(Map<String, dynamic> json) => VideoItem(
        name: '${json['name'] ?? ''}',
        sizeText: '${json['size_text'] ?? ''}',
        createTime: '${json['create_time'] ?? ''}',
        url: '${json['url'] ?? ''}',
      );
}
