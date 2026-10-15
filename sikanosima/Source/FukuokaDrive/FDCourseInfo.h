#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Engine/Texture2D.h"
#include "FDCourseInfo.generated.h"

/**
 * コースごとに違う値 (ミニマップの地図の範囲など) をレベルに持たせる。
 * tools/ue/setup_project.py がコースのレベルに 1 つ置く。無いレベルでは各クラスの既定値 (糸島一周) のまま。
 * 読むのは AFDBikePawn (ミニマップ) と AFDTimeOfDay (太陽と星の緯度経度)。
 */
UCLASS()
class FUKUOKADRIVE_API AFDCourseInfo : public AActor
{
	GENERATED_BODY()

public:
	AFDCourseInfo();

	/** コースの名前 (tools/terrain/areas/<名前>.json) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course")
	FString CourseName;

	/** ミニマップの地図 (空なら AFDBikePawn の既定の地図) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course")
	TSoftObjectPtr<UTexture2D> MinimapTexture;

	/** ミニマップの地図の左上 (北西の角) の UE 座標 (cm)。build_minimap.py が書く minimap.json の値 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course")
	FVector2D MinimapWorldMin = FVector2D::ZeroVector;

	/** ミニマップの地図の右下 (南東の角) の UE 座標 (cm) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course")
	FVector2D MinimapWorldMax = FVector2D::ZeroVector;

	/** 太陽と星の計算に使う緯度 (度) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course")
	float Latitude = 33.641f;

	/** 太陽と星の計算に使う経度 (度) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course")
	float Longitude = 130.196f;

	/** タイルの升目の回転 (度、反時計回り。areas/<コース>.json の rotation_deg)。0 なら UE の -Y が北。
	 *  回っているときの真北は UE の (sin, -cos) の向き。太陽・月・星とミニマップの N が使う */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Course")
	float GridRotationDeg = 0.f;

	/** レベルにある AFDCourseInfo (無ければ nullptr) */
	static const AFDCourseInfo* Find(const UWorld* World);

	bool HasMinimapBounds() const { return MinimapWorldMax.X > MinimapWorldMin.X && MinimapWorldMax.Y > MinimapWorldMin.Y; }
};
