#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "FDEditorTools.generated.h"

class ALandscape;
class ULandscapeLayerInfoObject;
class UMaterialInterface;

/**
 * tools/ue/setup_project.py から呼ぶエディタ用の処理。UE 5.8 の Python にはハイトマップからランドスケープを
 * 作る関数が無いので、エディタの「新規ランドスケープ → ファイルからインポート」と同じことを C++ で行う。
 * エディタの外 (パッケージしたゲーム) では何もしない。
 */
UCLASS()
class FUKUOKADRIVE_API UFDEditorTools : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	/**
	 * ハイトマップ (16bit RAW、リトルエンディアン、32768 = 海面) と道路レイヤーの重み (8bit RAW) から
	 * Size x Size 頂点のランドスケープを作る。Size - 1 は 126 (63 クワッド x 2 セクション) の倍数。
	 * CornerLocation は北西の角 (UE の最小 X, Y)。World Partition のレベルでも 1 つのアクターのまま
	 * (ストリーミング用に分けない) なので、どこにいても読み込まれている。
	 */
	UFUNCTION(BlueprintCallable, Category = "FukuokaDrive|Editor", meta = (WorldContext = "WorldContextObject"))
	static ALandscape* CreateLandscape(UObject* WorldContextObject, const FString& HeightmapPath, int32 Size,
		FVector CornerLocation, FVector Scale, UMaterialInterface* Material, ULandscapeLayerInfoObject* RoadLayerInfo,
		const FString& RoadWeightPath, const FString& Label);

	/**
	 * World Partition のストリーミングを切る (ワールド設定の「Enable Streaming」と同じ)。切るとプレイ中も
	 * すべてのアクターが読み込まれたままになる。Python からは bEnableStreaming が見えないのでここで行う。
	 * 切った (もともと切れていた) ら true。
	 */
	/**
	 * ランドスケープのレイヤー情報 (エディタの「レイヤー情報を作成」と同じ) を PackagePath (例 /Game/X/Road_LayerInfo)
	 * に作る。保存は呼んだ側で行う。もうあればそれを返す。Python からはレイヤー名を書けないのでここで行う。
	 */
	UFUNCTION(BlueprintCallable, Category = "FukuokaDrive|Editor")
	static ULandscapeLayerInfoObject* CreateLayerInfo(const FString& PackagePath, FName LayerName);

	UFUNCTION(BlueprintCallable, Category = "FukuokaDrive|Editor", meta = (WorldContext = "WorldContextObject"))
	static bool DisableWorldPartitionStreaming(UObject* WorldContextObject);
};
