#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "FDMenu.h"
#include "FDWalkerCharacter.generated.h"

class AFDBikePawn;
class AFDTravelPoint;
class UCameraComponent;
class UInputAction;
class UInputMappingContext;
class UMaterialInterface;
class USpringArmComponent;
class UStaticMesh;
class UStaticMeshComponent;
class UTexture2D;
struct FInputActionValue;

/**
 * クロスカブを降りて歩く人 (三人称)。バイクの E キーで降りるとバイクの左に出て、バイクの近くで E を押すと乗る。
 *
 * - W/A/S/D で歩く (カメラの向きが前)。Shift を押している間は走る。Space でジャンプ。マウスで見回す
 * - 地面はランドスケープの当たり判定に乗る (景観物には当たり判定がないので、木やガードレールは通り抜ける)
 * - 海には入らない: 足もとが海面より MaxWadeDepthCm 深くなったら、直前に立っていた所へ戻す
 * - ミニマップ (止めてあるバイクも印で出る) とファストトラベル (バイクも一緒に移る) はバイクと同じように使える
 *
 * 見た目は tools/vehicle/build_walker.py で作った人形 (胴・上腕・前腕・太もも・すね) を関節ごとに組み立て、
 * 歩く速さに合わせて手足を振り、膝と肘を曲げる。メッシュがまだ取り込まれていないときはエンジン付属の基本形状で代わりに組む。
 */
UCLASS()
class FUKUOKADRIVE_API AFDWalkerCharacter : public ACharacter
{
	GENERATED_BODY()

public:
	/** カプセルの半分の高さ (cm)。身長 180cm 弱 */
	static constexpr float CapsuleHalfHeightCm = 88.f;
	/** 地面からカプセルの中心までの高さ (cm)。出すときに地面に埋まらないよう少し浮かせる */
	static constexpr float StandHeightCm = CapsuleHalfHeightCm + 2.f;

	AFDWalkerCharacter();

	virtual void Tick(float DeltaSeconds) override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	virtual void PawnClientRestart() override;
	virtual void UnPossessed() override;

	/** 降りてきたバイク (乗るとき、R で戻るとき、ファストトラベルで一緒に運ぶときに使う) */
	void SetBike(AFDBikePawn* InBike) { Bike = InBike; }

	UFUNCTION(BlueprintPure, Category = "Walker")
	AFDBikePawn* GetBike() const { return Bike; }

	/** バイクの近く (RideReachCm 以内) にいれば乗る (E キー) */
	UFUNCTION(BlueprintCallable, Category = "Walker")
	void GetOn();

	/** カメラの位置から自由に飛び回る (B キー、もう一度 B でここへ戻る) */
	UFUNCTION(BlueprintCallable, Category = "Walker")
	void StartFlying();

	/** バイクの横へ戻る (R キー) */
	UFUNCTION(BlueprintCallable, Category = "Walker")
	void ReturnToBike();

	/** ファストトラベルのメニューを開く / 閉じる (F キー) */
	UFUNCTION(BlueprintCallable, Category = "Walker")
	void ToggleTravelMenu();

	/** 行き先へ移る。バイクも一緒に移り、その横に立つ */
	UFUNCTION(BlueprintCallable, Category = "Walker")
	void TravelTo(const AFDTravelPoint* Point);

	/** 歩く速さ (cm/s)。150 で 5.4 km/h */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Walker")
	float WalkSpeedCms = 150.f;

	/** 走る速さ (cm/s)。450 で 16 km/h */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Walker")
	float RunSpeedCms = 450.f;

	/** バイクに乗れる距離 (cm、バイクの中心から) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Walker")
	float RideReachCm = 250.f;

	/** 海に入れる深さ (cm)。足もとが海面 (Z=0) よりこれだけ深くなると、直前に立っていた所へ戻す */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Walker")
	float MaxWadeDepthCm = 25.f;

	/** 画面左上に速度と操作を表示する */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Walker")
	bool bShowDebugText = true;

	// --- 人形の色 (リニア) ---

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Walker|見た目")
	FLinearColor SkinColor = FLinearColor(0.55f, 0.36f, 0.25f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Walker|見た目")
	FLinearColor HairColor = FLinearColor(0.02f, 0.015f, 0.01f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Walker|見た目")
	FLinearColor JacketColor = FLinearColor(0.22f, 0.20f, 0.11f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Walker|見た目")
	FLinearColor PantsColor = FLinearColor(0.04f, 0.06f, 0.13f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Walker|見た目")
	FLinearColor ShoeColor = FLinearColor(0.03f, 0.03f, 0.03f);

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USpringArmComponent> SpringArm;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<UCameraComponent> Camera;

	/** 人形の根もと (足の裏の高さ)。歩くと少し上下する */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USceneComponent> Figure;

	// 手足の付け根 (股関節・肩)。ここを前後に回して振る
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USceneComponent> LeftHip;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USceneComponent> RightHip;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USceneComponent> LeftShoulder;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USceneComponent> RightShoulder;

	// 膝と肘。脚を前へ出すときに膝を曲げ、肘はいつも少し曲げておく
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USceneComponent> LeftKnee;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USceneComponent> RightKnee;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USceneComponent> LeftElbow;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Components")
	TObjectPtr<USceneComponent> RightElbow;

	// 人形のメッシュ (tools/vehicle/build_walker.py の出力を setup_project.py が取り込む)
	UPROPERTY(EditAnywhere, Category = "Walker|見た目")
	TSoftObjectPtr<UStaticMesh> BodyMeshAsset;

	UPROPERTY(EditAnywhere, Category = "Walker|見た目")
	TSoftObjectPtr<UStaticMesh> UpperArmMeshAsset;

	UPROPERTY(EditAnywhere, Category = "Walker|見た目")
	TSoftObjectPtr<UStaticMesh> ForearmMeshAsset;

	UPROPERTY(EditAnywhere, Category = "Walker|見た目")
	TSoftObjectPtr<UStaticMesh> ThighMeshAsset;

	UPROPERTY(EditAnywhere, Category = "Walker|見た目")
	TSoftObjectPtr<UStaticMesh> ShinMeshAsset;

private:
	/** 人形の部品の色の種類 */
	enum class EPartColor : uint8 { Skin, Hair, Jacket, Pants, Shoe };

	UStaticMeshComponent* MakePart(USceneComponent* Parent, const TCHAR* Name, UStaticMesh* PartMesh, const FVector& Location,
	                               const FVector& Scale, EPartColor Color);
	/** 取り込んだメッシュを置く部品 (関節が原点。bMirror なら左右を反転して左側に使う) */
	UStaticMeshComponent* MakeFigureMesh(USceneComponent* Parent, const TCHAR* Name, bool bMirror);
	FLinearColor GetPartColor(EPartColor Color) const;
	/** 取り込んだメッシュがあればそれに替え、基本形状の部品を隠す */
	void ApplyFigureMeshes();
	void ApplyColors();
	void CreateInputAssets();
	void ShowMinimap();
	void HideMinimap();
	void UpdateLimbs(float DeltaSeconds);
	void KeepOutOfSea();
	float DistanceToBikeCm() const;

	void OnMove(const FInputActionValue& Value);
	/** カメラを回す (度、X = 右、Y = 上) */
	void Look(const FVector2D& DeltaDeg);

	UPROPERTY(Transient)
	TObjectPtr<AFDBikePawn> Bike;

	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> PartMeshes;

	/** PartMeshes と同じ並びの色の種類 */
	TArray<EPartColor> PartColors;

	/** 取り込んだメッシュを置く部品 (胴・左右の上腕・前腕・太もも・すね)。どれも色はスロットの名前で決める */
	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> FigureMeshes;

	/** 基本形状の部品 (取り込んだメッシュを使うときは隠す) */
	UPROPERTY()
	TArray<TObjectPtr<UStaticMeshComponent>> FallbackParts;

	bool bUsingFigureMeshes = false;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> ShapeMaterial;

	UPROPERTY(Transient)
	TObjectPtr<UInputMappingContext> MappingContext;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> MoveAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> LookAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> LookStickAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> RunAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> JumpAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> RideAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> ReturnAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> TravelMenuAction;

	UPROPERTY(Transient)
	TObjectPtr<UInputAction> FlyAction;

	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> LoadedMinimapTexture;

	FFDMenu Menu;
	TSharedPtr<SWidget> Minimap;

	bool bRunning = false;
	float StridePhase = 0.f;
	float SwingDeg = 0.f;
	FVector LastSafeLocation = FVector::ZeroVector;
};
