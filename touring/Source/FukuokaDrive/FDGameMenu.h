#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "FDMenu.h"
#include "FDGameMenu.generated.h"

class AFDTimeOfDay;
class UTexture2D;
class UInputAction;
class UInputMappingContext;

/**
 * Tab キーで開く設定のメニューと、M キーで開く拡大マップ (クリックした所へファストトラベル)。
 * バイク・歩いている人・飛んでいるカメラのどれを操作していても同じように使える。AFDGameMode がプレイ開始時に置く。
 *
 * メニューで切り替えられるもの: 走る地域、地図とファストトラベル、行き先の一覧、時刻、季節、カメラ、車体の色、音、
 * ミニマップと画面の文字の表示、自由飛行、バイクの乗り降り。個別のキー (F, N, V, B, Y, T/G, 1-4, E, R) もそのまま使える。
 */
UCLASS()
class FUKUOKADRIVE_API AFDGameMenu : public AActor
{
	GENERATED_BODY()

public:
	AFDGameMenu();

	/** Tab のメニューを開く / 閉じる */
	UFUNCTION(BlueprintCallable, Category = "Menu")
	void ToggleMenu();

	/** 拡大マップを開く / 閉じる (M キー) */
	UFUNCTION(BlueprintCallable, Category = "Menu")
	void ToggleMap();

	/** XY (UE 座標 cm) へ、いま操作しているものごと移る。Yaw が無ければ向きはそのまま。移れないときは理由を返す (移れたら空) */
	FString TravelTo(const FVector2D& XY, TOptional<float> Yaw);

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	void CreateInput();
	/** FocusIndex の行にカーソルを置いてメニューを開く (切り替えたあと同じ行で開き直す) */
	void OpenMain(int32 FocusIndex = INDEX_NONE);
	void OpenTimeMenu();
	/** 走る地域を選ぶ一覧。起動画面ではプレイ開始時に開く (起動画面の Tab はこの一覧を出し直す) */
	void OpenRegions();
	APlayerController* GetPC() const;
	AFDTimeOfDay* FindTimeOfDay() const;
	/** XY の地面 (海面より上) を探す。見つからなければ false (海の上) */
	bool FindLand(const FVector2D& XY, FVector& OutPoint) const;

	UPROPERTY(Transient)
	TObjectPtr<UInputMappingContext> MappingContext;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> MenuAction;
	UPROPERTY(Transient)
	TObjectPtr<UInputAction> MapAction;
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> LoadedMapTexture;

	enum class EOpen : uint8 { None, Main, Map };
	EOpen OpenKind = EOpen::None;
	FFDMenu Menu;
};
