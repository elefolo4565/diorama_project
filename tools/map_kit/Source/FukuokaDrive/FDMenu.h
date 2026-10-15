#pragma once

#include "CoreMinimal.h"

class APlayerController;
class AFDTravelPoint;
class SWidget;
class UGameViewportClient;
class UWorld;

/**
 * 画面の左に出す選択メニュー (車体色・ファストトラベル)。バイクと徒歩の両方で使う。
 * 開いているあいだはマウスのカーソルを出し、閉じるとゲームの操作に戻す。
 */
class FFDMenu
{
public:
	/** メニューの1行。Swatch があれば色見本を出す */
	struct FItem
	{
		FString Label;
		TOptional<FLinearColor> Swatch;
		bool bCurrent = false;
		TFunction<void()> OnPick;
	};

	void Open(APlayerController* PC, const FString& Title, TArray<FItem> Items, const FString& Footer);
	void Close();
	bool IsOpen() const { return Widget.IsValid(); }

	/** ファストトラベルの行き先を並べたメニューを開く。選ぶと Travel が呼ばれる */
	void OpenTravel(APlayerController* PC, TFunction<void(const AFDTravelPoint*)> Travel);

	/** レベルにある行き先を並び順で */
	static TArray<AFDTravelPoint*> GetTravelPoints(UWorld* World);

private:
	TSharedPtr<SWidget> Widget;
	TWeakObjectPtr<APlayerController> Owner;
	TWeakObjectPtr<UGameViewportClient> Viewport;
};
