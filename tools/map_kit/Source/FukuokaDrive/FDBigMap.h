#pragma once

#include "CoreMinimal.h"
#include "Styling/SlateBrush.h"
#include "Widgets/SLeafWidget.h"

class APawn;
class UTexture2D;

/**
 * 画面いっぱいに出す拡大マップ (M キー、Tab のメニューからも開く)。コース全体の地図にプレイヤーと行き先を出し、
 * クリックした所へファストトラベルする。行き先 (◆) の近くをクリックするとその行き先へ、それ以外はクリックした地点へ。
 * ホイールで拡大・縮小、ドラッグで地図を動かす。地図は SFDMinimap と同じ画像 (UE の +X が右、+Y が下)。
 */
class SFDBigMap : public SLeafWidget
{
public:
	/** 地図に出す行き先 */
	struct FPoint
	{
		FVector2D Location = FVector2D::ZeroVector;
		FString Label;
	};

	/** クリックした地点 (UE 座標 cm) と、近くの行き先の番号 (無ければ INDEX_NONE)。移れないときは理由を返す (移れたら空) */
	DECLARE_DELEGATE_RetVal_TwoParams(FString, FOnPick, const FVector2D& /*World*/, int32 /*PointIndex*/);

	SLATE_BEGIN_ARGS(SFDBigMap)
		: _MapTexture(nullptr)
		, _MapMin(FVector2D::ZeroVector)
		, _MapMax(FVector2D::ZeroVector)
		, _GridRotationDeg(0.f)
	{}
		/** いまのプレイヤー (バイク・歩いている人・飛んでいるカメラ) */
		SLATE_ARGUMENT(TWeakObjectPtr<const APawn>, Player)
		/** 降りて止めてあるバイク */
		SLATE_ARGUMENT(TWeakObjectPtr<const AActor>, ParkedBike)
		SLATE_ARGUMENT(UTexture2D*, MapTexture)
		/** 地図の画像の左上と右下の UE 座標 (cm) */
		SLATE_ARGUMENT(FVector2D, MapMin)
		SLATE_ARGUMENT(FVector2D, MapMax)
		SLATE_ARGUMENT(TArray<FPoint>, Points)
		/** コースの升目の回転 (度)。N の矢印を真北へ向ける */
		SLATE_ARGUMENT(float, GridRotationDeg)
		SLATE_EVENT(FOnPick, OnPick)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;
	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	                      FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle,
	                      bool bParentEnabled) const override;

	virtual bool SupportsKeyboardFocus() const override { return true; }
	virtual FReply OnMouseButtonDown(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseButtonUp(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseMove(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseWheel(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual void OnMouseLeave(const FPointerEvent& MouseEvent) override;

private:
	/** 地図全体が収まるときの 1 ピクセルあたりの cm を Zoom で割ったもの */
	double CmPerPx(const FVector2f& Size) const;
	FVector2f WorldToLocal(const FVector2D& World, const FVector2f& Size) const;
	FVector2D LocalToWorld(const FVector2f& Local, const FVector2f& Size) const;
	/** Local の近く (画面で PickRadiusPx 以内) にある行き先 */
	int32 FindPoint(const FVector2f& Local, const FVector2f& Size) const;
	void ClampView();

	TWeakObjectPtr<const APawn> Player;
	TWeakObjectPtr<const AActor> ParkedBike;
	FSlateBrush MapBrush;
	bool bHasMap = false;
	FVector2D MapMin = FVector2D::ZeroVector;
	FVector2D MapMax = FVector2D::ZeroVector;
	float GridRotationDeg = 0.f;
	TArray<FPoint> Points;
	FOnPick OnPick;

	/** 見ている中心 (UE 座標 cm) と拡大率 (1 で地図全体) */
	FVector2D ViewCenter = FVector2D::ZeroVector;
	double Zoom = 1.0;

	bool bPressed = false;
	bool bDragged = false;
	FVector2f PressLocal = FVector2f::ZeroVector;
	FVector2D PressViewCenter = FVector2D::ZeroVector;
	TOptional<FVector2f> HoverLocal;

	/** 移れなかったときの知らせと、出し続ける残り時間 */
	FString Message;
	double MessageUntil = 0.0;
};
