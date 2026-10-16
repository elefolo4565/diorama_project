#pragma once

#include "CoreMinimal.h"

class UObject;
class UWorld;

/**
 * ツーリングシミュレータの地域 (走るマップ)。1 地域 = 1 つの UE のコンテンツプラグイン。
 * プラグインの .uplugin の Category が "Touring Region" のものを地域とみなし、レベルは /<プラグイン名>/Maps/<プラグイン名>。
 * 地域のフォルダは tools/kit/install_kit.py --add-region が作り、setup_project.py がレベルとアセットを入れる。
 */
struct FFDRegion
{
	/** プラグイン名 (Sikanosima など) */
	FString Name;
	/** メニューに出す名前 (.uplugin の FriendlyName。志賀島 など) */
	FString DisplayName;
	/** .uplugin の Description */
	FString Description;
	/** レベルのパッケージ名 (/Sikanosima/Maps/Sikanosima) */
	FString MapPackage;
};

struct FFDRegions
{
	/** 起動画面のレベル (地域を選ぶだけの空のレベル)。setup_project.py の START_MAP_PATH と同じ */
	static const TCHAR* const StartMap;

	/** 使える地域 (レベルができているもの) を名前の順で */
	static TArray<FFDRegion> Find();

	/** いまのレベルが起動画面か */
	static bool IsStartMap(const UWorld* World);

	/** いまのレベルのパッケージ名 (/Sikanosima/Maps/Sikanosima。PIE の接頭辞は外す) */
	static FString CurrentMapPackage(const UWorld* World);

	/** 最後に選んだ地域のプラグイン名 (GameUserSettings.ini。無ければ空) */
	static FString LastRegion();

	/** 地域のレベルを開く。最後に選んだ地域として覚える */
	static void Open(UObject* WorldContext, const FFDRegion& Region);
};
